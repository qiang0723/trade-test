#!/usr/bin/env python3
"""
L1 Advisory Layer - Python测试运行器
用途：跨平台运行所有固化测试用例
"""

import sys
import os
import time
import subprocess
from pathlib import Path


# 测试配置
TEST_CATEGORIES = {
    "P0级别Bug修复测试": [
        ("test_p0_percentage_scale_bugfix.py", "P0-BugFix-1: 百分比口径统一"),
        ("test_p0_volume_scale_bugfix.py", "P0-BugFix-2: 成交量计算修正"),
        ("test_p0_volume_unit_bugfix.py", "P0-BugFix-3: 单位一致性"),
        ("test_p0_required_fields_bugfix.py", "P0-BugFix-4: 字段完整性"),
    ],
    "数据验证测试": [
        ("test_data_validation_completeness.py", "数据验证: 字段完整性"),
        ("test_data_validation_ranges.py", "数据验证: 数值合理性范围"),
    ],
}


class Colors:
    """终端颜色"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def print_header(text):
    """打印标题"""
    print("=" * 80)
    print(text)
    print("=" * 80)
    print()


def print_section(text):
    """打印分类标题"""
    print()
    print("=" * 80)
    print(text)
    print("=" * 80)
    print()


def run_test(test_file, test_name):
    """运行单个测试"""
    print("-" * 80)
    print(f"测试: {test_name}")
    print(f"文件: {test_file}")
    print("-" * 80)
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # 打印测试输出
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ PASS{Colors.NC}: {test_name}")
            return True
        else:
            print(f"{Colors.RED}❌ FAIL{Colors.NC}: {test_name}")
            return False
    
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}❌ TIMEOUT{Colors.NC}: {test_name} (超过60秒)")
        return False
    except Exception as e:
        print(f"{Colors.RED}❌ ERROR{Colors.NC}: {test_name}")
        print(f"错误: {e}")
        return False
    finally:
        print()


def main():
    """主函数"""
    print_header("L1 Advisory Layer - 完整测试套件")
    
    start_time = time.time()
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    # 运行所有测试分类
    for category_name, tests in TEST_CATEGORIES.items():
        print_section(f"{category_name}（{len(tests)}个）")
        
        for test_file, test_name in tests:
            test_path = Path(__file__).parent / test_file
            
            if not test_path.exists():
                print(f"{Colors.YELLOW}⚠️ SKIP{Colors.NC}: {test_name}")
                print(f"文件不存在: {test_file}")
                print()
                continue
            
            total_tests += 1
            
            if run_test(str(test_path), test_name):
                passed_tests += 1
            else:
                failed_tests.append(test_name)
    
    # 统计结果
    end_time = time.time()
    duration = int(end_time - start_time)
    
    print_header("测试完成")
    
    print(f"总计: {total_tests} 个测试")
    print(f"{Colors.GREEN}通过: {passed_tests}{Colors.NC}")
    
    if failed_tests:
        print(f"{Colors.RED}失败: {len(failed_tests)}{Colors.NC}")
        print()
        print("失败的测试:")
        for test_name in failed_tests:
            print(f"  - {test_name}")
    else:
        print("失败: 0")
    
    print(f"耗时: {duration}秒")
    print()
    
    # 返回状态
    if not failed_tests:
        print(f"{Colors.GREEN}✅ 所有测试通过！{Colors.NC}")
        print()
        return 0
    else:
        print(f"{Colors.RED}❌ 有测试失败，请检查！{Colors.NC}")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
