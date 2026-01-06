"""
Jcl.py 单元测试

测试场景:
1. SORT 输出 + 显式定义属性
2. SORT 输出 + 继承属性
3. DISP=NEW 创建者优先
4. 纯外部数据集 (只有 SHR)
5. 复杂 DISP 格式解析
6. 多 STEP 混合场景
"""

import os
import sys
import logging

# 配置简单的日志
logging.basicConfig(level=logging.INFO, format='%(message)s')

# --- MOCK 依赖库 ---
# 为了在没有安装 openpyxl/xlwings 的环境中运行测试，
# 我们在导入 Jcl 之前对这些模块进行 Mock
from unittest.mock import MagicMock
sys.modules['openpyxl'] = MagicMock()
sys.modules['xlwings'] = MagicMock()

# Mock logging.FileHandler 以避免路径错误
class MockFileHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()
    def emit(self, record):
        pass

logging.FileHandler = MockFileHandler
# ------------------

# 引入目标模块
import Jcl


def run_test(name: str, jcl_content: str, target_dsn: str, 
             expected_z: str, expected_status: str, expected_step: str = None):
    """
    通用测试执行器
    
    Args:
        name: 测试名称
        jcl_content: JCL 内容
        target_dsn: 目标数据集名
        expected_z: 期望的 Z 列值
        expected_status: 期望的状态
        expected_step: 期望的 STEP (可选)
    """
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"{'='*60}")
    
    filename = f"temp_test_{name.replace(' ', '_')}.jcl"
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(jcl_content)
    
    try:
        parser = Jcl.JCLParser(filename)
        
        mock_group_rows = [{
            'dataset': target_dsn,
            'recfm_val': 'FB',
            'lrecl_val': '100',
            'blksize_val': '1000',
            'needs_process': True
        }]
        
        resolver = Jcl.AttributeResolver(mock_group_rows)
        result, status = resolver.resolve(target_dsn, parser)
        
        if result:
            z_val = result.get("Z", "")
            status_val = result.get("STATUS", "")
            meta = result.get("META", {})
            step_val = meta.get("STEP", "")
            
            print(f"  目标 DSN: {target_dsn}")
            print(f"  Z 列: {z_val} (期望: {expected_z})")
            print(f"  状态: {status_val} (期望: {expected_status})")
            if expected_step:
                print(f"  STEP: {step_val} (期望: {expected_step})")
            
            # 验证
            passed = True
            if z_val != expected_z:
                print(f"  ❌ Z 列不匹配!")
                passed = False
            if status_val != expected_status:
                print(f"  ❌ 状态不匹配!")
                passed = False
            if expected_step and step_val != expected_step:
                print(f"  ❌ STEP 不匹配!")
                passed = False
            
            if passed:
                print(f"\n  🟢 通过")
                return True
            else:
                print(f"\n  🔴 失败")
                return False
        else:
            print(f"  ❌ 未找到匹配: {status}")
            return False
    
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_sort_explicit():
    """测试 1: SORT 输出 + 显式定义"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=SORT
//SORTIN   DD DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)
    """
    return run_test(
        "SORT 显式定义",
        jcl,
        "OUTPUT.DATA",
        expected_z="显式定义",
        expected_status="完成(显式)",
        expected_step="STEP01"
    )


def test_sort_inherit():
    """测试 2: SORT 输出 + 继承属性"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=SORT
//SORTIN   DD DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
    """
    # 这个测试需要特殊处理：需要把输入 DSN 也加入 mock 数据
    print(f"\n{'='*60}")
    print(f"测试: SORT 继承属性")
    print(f"{'='*60}")
    
    filename = "temp_test_sort_inherit.jcl"
    target_dsn = "OUTPUT.DATA"
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(jcl)
    
    try:
        parser = Jcl.JCLParser(filename)
        
        # 关键：mock 数据需要包含输入 DSN (INPUT.DATA) 才能继承
        mock_group_rows = [
            {
                'dataset': 'OUTPUT.DATA',
                'recfm_val': '',
                'lrecl_val': '',
                'blksize_val': '',
                'needs_process': True
            },
            {
                'dataset': 'INPUT.DATA',  # 输入源必须在 dsn_map 中
                'recfm_val': 'FB',
                'lrecl_val': '100',
                'blksize_val': '1000',
                'needs_process': False
            }
        ]
        
        resolver = Jcl.AttributeResolver(mock_group_rows)
        result, status = resolver.resolve(target_dsn, parser)
        
        if result:
            z_val = result.get("Z", "")
            status_val = result.get("STATUS", "")
            
            print(f"  目标 DSN: {target_dsn}")
            print(f"  Z 列: {z_val} (期望: INPUT.DATA)")
            print(f"  状态: {status_val} (期望: 完成(继承))")
            
            if z_val == "INPUT.DATA" and status_val == "完成(继承)":
                print(f"\n  🟢 通过")
                return True
            else:
                print(f"\n  🔴 失败")
                return False
        else:
            print(f"  ❌ 未找到匹配: {status}")
            return False
    
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_new_creator():
    """测试 3: DISP=NEW 创建者优先 (非 SORT)"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=READER
//INFILE   DD DSN=MY.DATA,DISP=SHR
//*
//STEP02   EXEC PGM=WRITER
//OUTFILE  DD DSN=MY.DATA,DISP=(NEW,CATLG)
    """
    return run_test(
        "NEW 创建者优先",
        jcl,
        "MY.DATA",
        expected_z="本JCL创建",
        expected_status="完成(创建)",
        expected_step="STEP02"
    )


def test_external_dataset():
    """测试 4: 纯外部数据集 (只有 SHR)"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=PROG1
//INFILE   DD DSN=EXTERNAL.DATA,DISP=SHR
//*
//STEP02   EXEC PGM=PROG2
//INPUT    DD DSN=EXTERNAL.DATA,DISP=SHR
    """
    return run_test(
        "外部数据集",
        jcl,
        "EXTERNAL.DATA",
        expected_z="外部数据集",
        expected_status="完成(外部)",
        expected_step="STEP01"
    )


def test_disp_complex_format():
    """测试 5: 复杂 DISP 格式"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=WRITER
//OUTFILE  DD DSN=TEST.DATA,DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,SPACE=(CYL,1)
    """
    return run_test(
        "复杂 DISP 格式",
        jcl,
        "TEST.DATA",
        expected_z="本JCL创建",
        expected_status="完成(创建)",
        expected_step="STEP01"
    )


def test_disp_parsing():
    """测试 6: DISP 参数解析"""
    print(f"\n{'='*60}")
    print("测试: DISP 参数解析")
    print(f"{'='*60}")
    
    # 创建临时解析器实例来测试 _extract_disp
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=TEST
//DD1      DD DSN=A,DISP=SHR
    """
    filename = "temp_disp_test.jcl"
    with open(filename, "w") as f:
        f.write(jcl)
    
    try:
        parser = Jcl.JCLParser(filename)
        
        test_cases = [
            ("DISP=SHR", "SHR"),
            ("DISP=NEW", "NEW"),
            ("DISP=OLD", "OLD"),
            ("DISP=MOD", "MOD"),
            ("DISP=(NEW,CATLG)", "NEW"),
            ("DISP=(NEW,CATLG,DELETE)", "NEW"),
            ("DISP=(,CATLG)", None),  # 空的第一参数
            ("DSN=TEST.DATA", None),  # 没有 DISP
        ]
        
        all_passed = True
        for line, expected in test_cases:
            result = parser._extract_disp(line)
            status = "✅" if result == expected else "❌"
            print(f"  {status} '{line}' -> {result} (期望: {expected})")
            if result != expected:
                all_passed = False
        
        if all_passed:
            print(f"\n  🟢 全部通过")
        else:
            print(f"\n  🔴 部分失败")
        return all_passed
    
    finally:
        if os.path.exists(filename):
            os.remove(filename)

# ==================== 边界情况和异常测试 ====================

def test_empty_jcl():
    """测试 7: 空 JCL 文件"""
    print(f"\n{'='*60}")
    print(f"测试: 空 JCL 文件")
    print(f"{'='*60}")
    
    jcl = """
//JOB1     JOB (123),'TEST'
//* 只有注释，没有任何 STEP
    """
    filename = "temp_test_empty.jcl"
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(jcl)
    
    try:
        parser = Jcl.JCLParser(filename)
        
        # 应该没有解析到任何 STEP
        if not parser.steps:
            print(f"  parser.steps 为空: ✅ 符合预期")
            print(f"\n  🟢 通过")
            return True
        else:
            print(f"  parser.steps 不为空: ❌ 不符合预期")
            print(f"\n  🔴 失败")
            return False
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_dsn_not_found():
    """测试 8: 目标 DSN 在 JCL 中不存在"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=PROG1
//INFILE   DD DSN=OTHER.DATA,DISP=SHR
    """
    print(f"\n{'='*60}")
    print(f"测试: DSN 不存在")
    print(f"{'='*60}")
    
    filename = "temp_test_notfound.jcl"
    target_dsn = "NOT.EXIST.DATA"
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(jcl)
    
    try:
        parser = Jcl.JCLParser(filename)
        resolver = Jcl.AttributeResolver([{'dataset': target_dsn, 'recfm_val': '', 'lrecl_val': '', 'blksize_val': '', 'needs_process': True}])
        result, status = resolver.resolve(target_dsn, parser)
        
        if result is None:
            print(f"  返回 None: ✅ 符合预期")
            print(f"  错误信息: {status}")
            print(f"\n  🟢 通过")
            return True
        else:
            print(f"  返回了结果: ❌ 不符合预期")
            print(f"\n  🔴 失败")
            return False
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_special_chars_dsn():
    """测试 9: DSN 包含特殊字符 (# @ $)"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=WRITER
//OUTFILE  DD DSN=SYS1.$PROD#DATA@SET,DISP=(NEW,CATLG)
    """
    return run_test(
        "特殊字符 DSN",
        jcl,
        "SYS1.$PROD#DATA@SET",
        expected_z="本JCL创建",
        expected_status="完成(创建)",
        expected_step="STEP01"
    )


def test_multi_new_same_dsn():
    """测试 10: 同一 DSN 在多个 STEP 中都有 NEW (应取第一个)"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=PROG1
//OUTFILE  DD DSN=MY.DATA,DISP=(NEW,CATLG)
//*
//STEP02   EXEC PGM=PROG2
//OUTFILE  DD DSN=MY.DATA,DISP=(NEW,CATLG)
    """
    return run_test(
        "多个 NEW 同一 DSN",
        jcl,
        "MY.DATA",
        expected_z="本JCL创建",
        expected_status="完成(创建)",
        expected_step="STEP01"  # 应该返回第一个
    )


def test_continuation_line():
    """测试 11: JCL 续行 (DD 参数跨多行)"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=SORT
//SORTIN   DD DSN=INPUT.DATA,DISP=SHR
//SORTOUT  DD DSN=OUTPUT.DATA,
//            DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,
//            SPACE=(CYL,(1,1)),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=800)
    """
    return run_test(
        "JCL 续行解析",
        jcl,
        "OUTPUT.DATA",
        expected_z="显式定义",
        expected_status="完成(显式)",
        expected_step="STEP01"
    )


def test_iebgener_program():
    """测试 12: IEBGENER 程序 (SYSUT2 作为输出)"""
    print(f"\n{'='*60}")
    print(f"测试: IEBGENER 程序")
    print(f"{'='*60}")
    
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=IEBGENER
//SYSUT1   DD DSN=INPUT.DATA,DISP=SHR
//SYSUT2   DD DSN=OUTPUT.DATA,DISP=(NEW,CATLG)
//SYSPRINT DD SYSOUT=*
//SYSIN    DD DUMMY
    """
    filename = "temp_test_iebgener.jcl"
    target_dsn = "OUTPUT.DATA"
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(jcl)
    
    try:
        parser = Jcl.JCLParser(filename)
        
        # mock 数据包含输入 DSN
        mock_group_rows = [
            {'dataset': 'OUTPUT.DATA', 'recfm_val': '', 'lrecl_val': '', 'blksize_val': '', 'needs_process': True},
            {'dataset': 'INPUT.DATA', 'recfm_val': 'FB', 'lrecl_val': '80', 'blksize_val': '800', 'needs_process': False}
        ]
        
        resolver = Jcl.AttributeResolver(mock_group_rows)
        result, status = resolver.resolve(target_dsn, parser)
        
        if result:
            z_val = result.get("Z", "")
            status_val = result.get("STATUS", "")
            
            print(f"  目标 DSN: {target_dsn}")
            print(f"  Z 列: {z_val} (期望: INPUT.DATA)")
            print(f"  状态: {status_val} (期望: 完成(继承))")
            
            # IEBGENER 的 SYSUT2 应该继承 SYSUT1 的属性
            if z_val == "INPUT.DATA" and status_val == "完成(继承)":
                print(f"\n  🟢 通过")
                return True
            else:
                print(f"\n  🔴 失败")
                return False
        else:
            print(f"  ❌ 未找到匹配: {status}")
            return False
    finally:
        if os.path.exists(filename):
            os.remove(filename)


def test_no_disp_param():
    """测试 13: DD 语句没有 DISP 参数"""
    jcl = """
//JOB1     JOB (123),'TEST'
//STEP01   EXEC PGM=PROG1
//INFILE   DD DSN=NO.DISP.DATA,UNIT=SYSDA
    """
    return run_test(
        "无 DISP 参数",
        jcl,
        "NO.DISP.DATA",
        expected_z="外部数据集",  # 没有 DISP 时 DISP 为 None，走外部数据集逻辑
        expected_status="完成(外部)",
        expected_step="STEP01"
    )


def test_mixed_case_keywords():
    """测试 14: 大小写混合的关键字"""
    jcl = """
//JOB1     JOB (123),'TEST'
//Step01   Exec Pgm=SORT
//SortIn   DD Dsn=INPUT.DATA,Disp=Shr
//SortOut  DD Dsn=OUTPUT.DATA,Disp=(New,Catlg),
//            DCB=(Recfm=FB,Lrecl=80,Blksize=800)
    """
    return run_test(
        "大小写混合",
        jcl,
        "OUTPUT.DATA",
        expected_z="显式定义",
        expected_status="完成(显式)",
        expected_step="Step01"
    )


def main():
    print("="*60)
    print("Jcl.py 单元测试")
    print("="*60)
    
    tests = [
        # 正常场景
        ("正常场景", [
            test_sort_explicit,
            test_sort_inherit,
            test_new_creator,
            test_external_dataset,
            test_disp_complex_format,
            test_disp_parsing,
        ]),
        # 边界情况
        ("边界情况", [
            test_empty_jcl,
            test_dsn_not_found,
            test_special_chars_dsn,
            test_multi_new_same_dsn,
            test_continuation_line,
            test_iebgener_program,
            test_no_disp_param,
            test_mixed_case_keywords,
        ]),
    ]
    
    all_results = []
    
    for category, test_list in tests:
        print(f"\n{'#'*60}")
        print(f"# {category}")
        print(f"{'#'*60}")
        
        for test in test_list:
            try:
                all_results.append(test())
            except Exception as e:
                print(f"\n  💥 异常: {e}")
                import traceback
                traceback.print_exc()
                all_results.append(False)
    
    # 汇总
    print(f"\n{'='*60}")
    print("测试汇总")
    print(f"{'='*60}")
    passed = sum(all_results)
    total = len(all_results)
    print(f"  通过: {passed}/{total}")
    
    if passed == total:
        print("\n  🎉 全部测试通过!")
    else:
        print(f"\n  ⚠️ {total - passed} 个测试失败")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
