"""测试日历时间解析功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from modules.calendar_module import CalendarModule


def test_time_parsing():
    """测试时间解析功能"""
    calendar = CalendarModule()
    
    test_cases = [
        ("明天下午3点", "普通时间"),
        ("明天下午3点半", "带分钟的时间"),
        ("下周一上午10点", "下周时间"),
        ("今天晚上7点", "今天晚上"),
        ("明天上午9点", "明天上午"),
        ("后天下午2点", "后天"),
        ("下周五下午4点", "下周五"),
        ("明天上午10点30分", "精确到分钟"),
        ("明天全天", "全天日程"),
        ("下周一全天", "下周一整天"),
    ]
    
    print("=" * 60)
    print("测试时间解析功能")
    print("当前时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    for time_str, description in test_cases:
        print(f"\n【{description}】输入: {time_str}")
        start_time, end_time, start_date, end_date = calendar._parse_natural_time(time_str)
        
        if start_date and end_date:
            print(f"  类型: 全天日程")
            print(f"  开始日期: {start_date}")
            print(f"  结束日期: {end_date}")
        else:
            print(f"  类型: 普通日程")
            print(f"  开始时间戳: {start_time}")
            print(f"  结束时间戳: {end_time}")
            
            if start_time:
                try:
                    start_dt = datetime.fromtimestamp(int(start_time))
                    end_dt = datetime.fromtimestamp(int(end_time))
                    print(f"  开始时间: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"  结束时间: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception as e:
                    print(f"  时间转换失败: {e}")


def test_missing_fields():
    """测试缺失字段检查"""
    calendar = CalendarModule()
    
    test_cases = [
        ({"summary": "测试日程", "start_time": "1234567890", "end_time": "1234567950"}, "完整参数"),
        ({"summary": "测试日程"}, "缺少时间"),
        ({"start_time": "1234567890", "end_time": "1234567950"}, "缺少标题"),
        ({}, "缺少所有必填字段"),
        ({"summary": "全天日程", "start_date": "2026-04-24", "end_date": "2026-04-25"}, "全天日程完整参数"),
        ({"summary": "全天日程", "start_date": "2026-04-24"}, "全天日程缺少结束日期"),
    ]
    
    print("\n" + "=" * 60)
    print("测试缺失字段检查")
    print("=" * 60)
    
    for params, description in test_cases:
        missing = calendar._get_missing_fields(params)
        print(f"\n【{description}】")
        print(f"  参数: {params}")
        print(f"  缺失字段: {missing if missing else '无'}")


if __name__ == "__main__":
    test_time_parsing()
    test_missing_fields()
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
