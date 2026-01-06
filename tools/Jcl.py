import os
import re
import shutil
import openpyxl
import logging
import time
from collections import defaultdict
from datetime import datetime
import xlwings as xw

# ================= ⚙️ 配置区域 =================
BASE_DIR = r"C:\Users\zhu-chaofan\Downloads"
JCL_DIR = os.path.join(BASE_DIR, r"JCL\JCL")  # JCL 根目录

SOURCE_FILE_NAME = "DSN_Final.xlsx"
OUTPUT_FILE_NAME = f"AssetList_Lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
LOG_FILE_NAME = f"Process_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

SOURCE_PATH = os.path.join(BASE_DIR, SOURCE_FILE_NAME)
TARGET_PATH = os.path.join(BASE_DIR, OUTPUT_FILE_NAME)
LOG_PATH = os.path.join(BASE_DIR, LOG_FILE_NAME)

# 🔥 核心配置：请确保 Excel 里真的有这个名字的 Sheet
TARGET_SHEET_NAME = "Sheet2"

# 批处理大小
BATCH_SIZE = 1000

# --- Excel 读取列 definition (1-based) ---
COL_JCL_NAME = 3   # C列: JCL名
COL_DATASET = 7    # G列: Dataset名
COL_RECFM = 12     # L列: RECFM (用于判断是否需要处理)
COL_LRECL = 13     # M列
COL_BLKSIZE = 14   # N列

# ================= 📝 日志模块 =================
def setup_logger(log_file_path):
    logger = logging.getLogger("Processor")
    logger.setLevel(logging.INFO)
    if logger.handlers: logger.handlers.clear()
    
    fh = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(fh)
    
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(ch)
    return logger

logger = setup_logger(LOG_PATH)

# ================= 🔍 辅助模块: 建立文件索引 =================
def build_filename_index(root_dir):
    """递归遍历目录，建立 {文件名(无后缀): 绝对路径} 映射"""
    logger.info(f"🕵️‍♂️ 正在建立文件索引 (扫描目录: {root_dir})...")
    file_map = {}
    count = 0
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            name_no_ext = os.path.splitext(file)[0]
            full_path = os.path.join(root, file)
            if name_no_ext not in file_map:
                file_map[name_no_ext] = full_path
            count += 1
    logger.info(f"✅ 索引构建完成。扫描文件总数: {count}")
    return file_map

# ================= 🧩 JCL 解析器 (全量捕捉) =================
class JCLParser:
    def __init__(self, filepath):
        self.filepath = filepath
        # 结构: { "STEP名": { "PGM": "XXX", "DDS": [ {name, dsn, ...} ] } }
        self.steps = {} 
        self._load_and_parse()

    def _load_and_parse(self):
        try:
            with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                raw_content = f.read()
            normalized_lines = self._normalize_jcl(raw_content)
            self._parse_lines(normalized_lines)
        except Exception as e:
            logger.error(f"❌ 读取 JCL 失败: {os.path.basename(self.filepath)} - {e}")

    def _normalize_jcl(self, content):
        """清洗 JCL，处理断行拼接"""
        lines = content.split('\n')
        cleaned_lines = []
        buffer = ""
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//*') or not line.startswith('//'): continue
            if line.endswith(','):
                if buffer:
                    clean_segment = re.sub(r'^//\s*', '', line)
                    buffer += clean_segment
                else:
                    buffer = line
            else:
                if buffer:
                    clean_segment = re.sub(r'^//\s*', '', line)
                    cleaned_lines.append(buffer + clean_segment)
                    buffer = ""
                else:
                    cleaned_lines.append(line)
        return cleaned_lines

    def _parse_lines(self, lines):
        """
        识别所有 STEP 和 DD。
        不再过滤非 SORT 程序，只要是 STEP 都记录。
        """
        current_step_name = None
        
        re_step = re.compile(r'^//(\S+)\s+EXEC\s+PGM=([A-Z0-9#@$]+)', re.IGNORECASE)
        re_dd = re.compile(r'^//(\S+)\s+DD\s+', re.IGNORECASE)

        for line in lines:
            # 1. STEP 识别
            step_match = re_step.search(line)
            if step_match:
                step_name = step_match.group(1)
                pgm_name = step_match.group(2).upper()
                
                current_step_name = step_name
                self.steps[step_name] = {
                    "PGM": pgm_name,
                    "DDS": []
                }
                continue

            # 2. DD 识别 (只要在 Step 内都抓)
            if current_step_name:
                dd_match = re_dd.search(line)
                if dd_match:
                    dd_name = dd_match.group(1).upper()
                    dsn = self._extract_param(line, "DSN")
                    if not dsn: continue
                    
                    attrs = {
                        "DD": dd_name,
                        "DSN": dsn,
                        "RECFM": self._extract_param(line, "RECFM"),
                        "LRECL": self._extract_param(line, "LRECL"),
                        "BLKSIZE": self._extract_param(line, "BLKSIZE")
                    }
                    self.steps[current_step_name]["DDS"].append(attrs)

    def _extract_param(self, line, key):
        match = re.search(f"{key}=([\\w\\.\\$#@\\(\\)]+)", line, re.IGNORECASE)
        if match: return match.group(1).replace('(', '').replace(')', '')
        return None

# ================= 🧠 业务推理机 (分级策略) =================
class AttributeResolver:
    def __init__(self, group_rows):
        self.dsn_map = {r['dataset']: r for r in group_rows if r['dataset']}
        self.SORT_PGM_LIST = {'SORT', 'ICEMAN', 'DFSORT', 'SYNCSORT', 'IEBGENER', 'ICEGENER'}
    
    def resolve(self, target_dsn, jcl_parser):
        if not jcl_parser or not jcl_parser.steps: 
            return None, "No Steps found"

        fallback_match = None # 兜底方案 (非SORT，或找不到血缘的引用)

        # 遍历所有 Step
        for step_name, step_data in jcl_parser.steps.items():
            pgm = step_data["PGM"]
            
            # 在当前 Step 找目标 DSN
            # (如果一个 Step 有多个同名 DSN，这里取第一个)
            target_dd = next((dd for dd in step_data["DDS"] if dd["DSN"] == target_dsn), None)
            
            if not target_dd: continue

            # === 基础元数据 (只要找到了，就能填 AG~AJ) ===
            meta_info = {
                "STEP": step_name,
                "PGM": pgm,
                "DD": target_dd["DD"]
            }
            
            # 策略：先记录一个“兜底结果”。
            # 如果后面也没发现这是个 SORT 输出，就返回这个结果。
            if not fallback_match:
                fallback_match = ({
                    "Z": "N/A (Ref Only)",    # Z: 仅引用，无血缘
                    "AA": target_dd["RECFM"], # AA: 也许 JCL 里写了
                    "AB": target_dd["LRECL"], # AB
                    "AC": target_dd["BLKSIZE"], # AC
                    "META": meta_info,
                    "STATUS": "Done (Ref)"    # AF: 状态
                }, "Reference Found")

            # === 高级逻辑: 只有 SORT 程序才尝试推导血缘 ===
            if pgm in self.SORT_PGM_LIST:
                dd_name = target_dd["DD"]
                is_output = dd_name.startswith("SORTOUT") or dd_name == "SYSUT2"
                
                if is_output:
                    # Logic A: 显式定义 (最高优先级之一)
                    if target_dd.get("LRECL") and target_dd.get("RECFM"):
                         return {
                            "Z": "N/A (Explicit)",
                            "AA": target_dd["RECFM"],
                            "AB": target_dd["LRECL"],
                            "AC": target_dd.get("BLKSIZE", ""),
                            "META": meta_info,
                            "STATUS": "Done (Explicit)"
                        }, "Sort Explicit"

                    # Logic B: 继承自输入 (最高优先级之二)
                    input_candidates = [d for d in step_data["DDS"] 
                                        if not (d["DD"].startswith("SORTOUT") or d["DD"] == "SYSUT2")]
                    
                    if input_candidates:
                        first_input = input_candidates[0]
                        source_dsn = first_input["DSN"]
                        
                        if source_dsn in self.dsn_map:
                            src_row = self.dsn_map[source_dsn]
                            return {
                                "Z": source_dsn, 
                                "AA": src_row['recfm_val'],
                                "AB": src_row['lrecl_val'],
                                "AC": src_row['blksize_val'],
                                "META": meta_info,
                                "STATUS": "Done (Inherited)"
                            }, "Sort Inherited"
        
        # 循环结束，如果没找到“高级血缘”，但找到了“普通引用”，返回兜底
        if fallback_match:
            return fallback_match
            
        return None, "Not found in JCL"

# ================= 🚀 主流程 =================
def main():
    start_time = time.time()
    logger.info(f"🚀 任务启动 | {datetime.now()}")

    if not os.path.exists(SOURCE_PATH):
        logger.error(f"❌ 找不到源文件: {SOURCE_PATH}"); return
    
    jcl_path_map = build_filename_index(JCL_DIR)
    
    logger.info(f"📂 复制文件: {SOURCE_FILE_NAME} -> {OUTPUT_FILE_NAME}")
    shutil.copy2(SOURCE_PATH, TARGET_PATH)

    # --- Phase 1: 读取 Excel ---
    logger.info(f"👀 [Phase 1] 读取数据 (Sheet: {TARGET_SHEET_NAME})...")
    wb_reader = openpyxl.load_workbook(TARGET_PATH, data_only=True, read_only=True)
    try:
        ws_reader = wb_reader[TARGET_SHEET_NAME]
    except KeyError:
        logger.error(f"❌ Excel 中找不到名为 '{TARGET_SHEET_NAME}' 的 Sheet！"); return

    groups = defaultdict(list)
    row_counter = 0
    beginRow = 108415  # 数据从第108415行开始

    for row in ws_reader.iter_rows(min_row=beginRow, values_only=True):
        row_counter += 1
        if row_counter % 50000 == 0: logger.info(f"   ...已扫描 {row_counter} 行")
        try:
            if len(row) < max(COL_JCL_NAME, COL_DATASET, COL_RECFM): continue
            jcl = row[COL_JCL_NAME-1]
            if not jcl: continue
            
            recfm_val = row[COL_RECFM-1]
            s_recfm = str(recfm_val).strip() if recfm_val is not None else ""
            if s_recfm.endswith(".0"): s_recfm = s_recfm[:-2]
            
            needs_process = (s_recfm == "0" or s_recfm == "")

            groups[jcl].append({
                "row_idx": row_counter + beginRow - 1,
                "dataset": row[COL_DATASET-1],
                "recfm_val": s_recfm,
                "lrecl_val": row[COL_LRECL-1],
                "blksize_val": row[COL_BLKSIZE-1],
                "needs_process": needs_process
            })
        except Exception: continue
    wb_reader.close()
    logger.info(f"✅ 扫描完成。发现 JCL 组数: {len(groups)}")

    # --- Phase 2: 计算逻辑 ---
    logger.info("🧠 [Phase 2] 解析 JCL 并构建血缘/元数据...")
    updates_buffer = [] 
    jcl_cache = {}
    
    for jcl_name, rows in groups.items():
        target_rows = [r for r in rows if r['needs_process']]
        if not target_rows: continue
        
        real_path = jcl_path_map.get(jcl_name)
        if not real_path: continue

        if jcl_name not in jcl_cache: jcl_cache[jcl_name] = JCLParser(real_path)
        
        parser = jcl_cache[jcl_name]
        resolver = AttributeResolver(rows)

        for target in target_rows:
            res_data, status = resolver.resolve(target['dataset'], parser)
            if res_data:
                meta = res_data.get("META", {})
                # 为防止 None 值写入报错，转换为 ""
                safe_val = lambda v: v if v else ""
                
                updates_buffer.append({
                    "row": target['row_idx'],
                    # Z ~ AC
                    "vals_attr": [
                        safe_val(res_data["Z"]), 
                        safe_val(res_data["AA"]), 
                        safe_val(res_data["AB"]), 
                        safe_val(res_data["AC"])
                    ],
                    # AF ~ AJ
                    "vals_meta": [
                        res_data.get("STATUS", "Done"), # AF: 标记状态
                        jcl_name,                       # AG: JCL名
                        safe_val(meta.get("STEP")),     # AH: STEP
                        safe_val(meta.get("PGM")),      # AI: PGM
                        safe_val(meta.get("DD"))        # AJ: DD
                    ]
                })

    # --- Phase 3: 分批回写 ---
    if updates_buffer:
        total = len(updates_buffer)
        logger.info(f"✍️ [Phase 3] 启动回填，共 {total} 条数据 (Sheet: {TARGET_SHEET_NAME})")
        
        app = xw.App(visible=True)
        app.screen_updating = False
        app.display_alerts = False
        
        try:
            wb = app.books.open(TARGET_PATH)
            app.calculation = 'manual' # 关闭自动计算
            
            try: ws = wb.sheets[TARGET_SHEET_NAME]
            except: ws = wb.sheets[0]

            for start_idx in range(0, total, BATCH_SIZE):
                end_idx = min(start_idx + BATCH_SIZE, total)
                current_batch = updates_buffer[start_idx : end_idx]
                
                print(f"\n--- ⚡ 正在处理第 {start_idx + 1} 到 {end_idx} 行 ---")
                t0 = time.time()
                
                for i, item in enumerate(current_batch):
                    r = item["row"]
                    # 1. 填物理属性 (Z-AC) => Z列是第26列
                    ws.range((r, 26)).value = item["vals_attr"]
                    
                    # 2. 填元数据 (AF-AJ) => AF列是第32列
                    # AF=32, AG=33, AH=34, AI=35, AJ=36
                    ws.range((r, 32)).value = item["vals_meta"]
                    
                    if i % 50 == 0: print(f"\r   ... 进度: {i}/{len(current_batch)}", end="")
                
                print(f"\n   ⏱️ 本批耗时: {time.time() - t0:.2f}s")
                wb.save()
                
                if end_idx < total:
                    # ⚠️ 注意: 自动化运行时建议注释掉下面这行 input
                    if input(f"   ❓ 继续? [Y/n] >> ").strip().lower() == 'n': break
        
        except Exception as e:
            logger.error(f"❌ 异常: {e}")
            import traceback; traceback.print_exc()
        finally:
            try:
                app.calculation = 'automatic' # 恢复设置
                app.screen_updating = True
                wb.close()
                app.quit()
                logger.info("👋 完成")
            except: pass
    else:
        logger.info("⚠️ 没有数据更新。")

    logger.info(f"🏁 总耗时: {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    main()