import os
import sys
import logging

# 引入目标模块
import Jcl

# 配置简单的日志
logging.basicConfig(level=logging.INFO, format='%(message)s')

def test_jcl_logic():
    print("="*60)
    print("测试用例: 验证当前代码是否无法区分 '创建者(NEW)' 和 '引用者(SHR)'")
    print("="*60)

    # 1. 构造测试 JCL 内容
    # 场景: DDDD 在 STEP01 中被引用 (SHR)，在 STEP02 中被创建 (NEW)
    # 按照当前逻辑，解析器会因为先遇到 STEP01 就直接将其判定为来源
    jcl_content = """
//JOBTEST  JOB (123),'TEST',CLASS=A
//* ------------------------------------------------
//* STEP01: 只是读取引用 (干扰项)
//* ------------------------------------------------
//STEP01   EXEC PGM=OLDPROG
//INDD     DD DSN=TEST.DATA.SET,DISP=SHR
//*
//* ------------------------------------------------
//* STEP02: 实际创建该文件 (正确答案)
//* ------------------------------------------------
//STEP02   EXEC PGM=NEWPROG
//OUTDD    DD DSN=TEST.DATA.SET,DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,SPACE=(CYL,(1,1)),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)
    """

    filename = "temp_reproduce_bug.jcl"
    target_dsn = "TEST.DATA.SET"

    # 写入临时文件
    with open(filename, "w", encoding='utf-8') as f:
        f.write(jcl_content)

    try:
        # 2. 调用 JCLParser 解析
        print(f"正在解析 JCL 文件: {filename}")
        parser = Jcl.JCLParser(filename)

        # 检查是否提取了 DISP 字段 (验证点 1)
        print("\n[检查点 1] 检查 parser 是否提取了 DISP 参数:")
        has_disp_extracted = False
        step02_data = parser.steps.get("STEP02")
        
        if step02_data:
            for dd in step02_data["DDS"]:
                if dd["DSN"] == target_dsn:
                    if "DISP" in dd:
                        print(f"  -> STEP02 中提取到了 DISP: {dd['DISP']}")
                        has_disp_extracted = True
                    else:
                        print(f"  -> STEP02 中未提取到 DISP 字段 (符合预期，当前未实现)")
        
        if not has_disp_extracted:
            print("  ==> 结论: JCLParser 需要升级以支持 DISP 提取")

        # 3. 调用 AttributeResolver 推导血缘 (验证点 2)
        print("\n[检查点 2] 模拟 AttributeResolver 寻找数据来源:")
        
        # 构造模拟的 Excel 行数据 (Resolver 初始化需要)
        mock_group_rows = [{
            'dataset': target_dsn, 
            'recfm_val': '', 
            'lrecl_val': '', 
            'blksize_val': '',
            'needs_process': True
        }]
        
        resolver = Jcl.AttributeResolver(mock_group_rows)
        result, status = resolver.resolve(target_dsn, parser)

        if result:
            meta = result.get("META", {})
            found_step = meta.get("STEP")
            found_pgm = meta.get("PGM")
            
            print(f"  目标 Dataset: {target_dsn}")
            print(f"  解析返回的来源 STEP: {found_step}")
            print(f"  解析返回的来源 PGM : {found_pgm}")
            
            if found_step == "STEP01":
                print("\n🔴 测试结果: 失败 (但符合当前预期)")
                print("  原因: 代码识别了第一个引用者 STEP01，而不是创建者 STEP02")
            elif found_step == "STEP02":
                print("\n🟢 测试结果: 成功")
                print("  原因: 代码正确识别了创建者")
            else:
                print(f"\n🟡 测试结果: 未知 ({found_step})")
        else:
            print("\nError: 未找到任何匹配")

    finally:
        # 清理临时文件
        if os.path.exists(filename):
            os.remove(filename)
    print("\n" + "="*60)

if __name__ == "__main__":
    test_jcl_logic()
