#!/usr/bin/env python3
"""
测试智能体与飞书服务器的连接稳定性
包含多种测试场景：基本连接、多次请求、超时、并发等
"""

import asyncio
import sys
import time
import statistics
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils import setup_logger, logger
from config import settings
from utils import get_feishu_client


class ConnectionStabilityTester:
    """连接稳定性测试器"""

    def __init__(self):
        self.client = get_feishu_client()
        self.test_results = []

    async def test_basic_connection(self) -> Dict[str, Any]:
        """测试基本连接 - 获取access_token"""
        print("\n" + "="*60)
        print("测试 1: 基本连接测试 (获取 access_token)")
        print("="*60)

        try:
            start_time = time.time()
            access_token = await self.client._get_access_token()
            end_time = time.time()
            latency = (end_time - start_time) * 1000  # 转换为毫秒

            if access_token:
                result = {
                    "test_name": "基本连接测试",
                    "success": True,
                    "latency_ms": round(latency, 2),
                    "token_length": len(access_token),
                    "message": f"连接成功，延迟: {latency:.2f}ms"
                }
                print(f"✅ 连接成功")
                print(f"   延迟: {latency:.2f}ms")
                print(f"   Token长度: {len(access_token)}")
            else:
                result = {
                    "test_name": "基本连接测试",
                    "success": False,
                    "latency_ms": round(latency, 2),
                    "message": "获取 access_token 失败"
                }
                print(f"❌ 连接失败: 获取 access_token 失败")

        except Exception as e:
            result = {
                "test_name": "基本连接测试",
                "success": False,
                "latency_ms": 0,
                "message": f"连接异常: {str(e)}"
            }
            print(f"❌ 连接异常: {str(e)}")
            logger.error(f"基本连接测试失败: {str(e)}", exc_info=True)

        self.test_results.append(result)
        return result

    async def test_multiple_connections(self, count: int = 5) -> Dict[str, Any]:
        """测试多次连接稳定性"""
        print("\n" + "="*60)
        print(f"测试 2: 多次连接稳定性测试 ({count} 次)")
        print("="*60)

        latencies = []
        success_count = 0
        failure_count = 0

        for i in range(count):
            try:
                print(f"\n  第 {i+1} 次连接测试...")
                start_time = time.time()
                access_token = await self.client._get_access_token()
                end_time = time.time()
                latency = (end_time - start_time) * 1000

                if access_token:
                    latencies.append(latency)
                    success_count += 1
                    print(f"  ✅ 成功，延迟: {latency:.2f}ms")
                else:
                    failure_count += 1
                    print(f"  ❌ 失败: Token为空")

            except Exception as e:
                failure_count += 1
                print(f"  ❌ 失败: {str(e)}")
                logger.error(f"第 {i+1} 次连接测试失败: {str(e)}")

            # 每次测试之间稍微延迟，避免请求过于频繁
            await asyncio.sleep(0.5)

        # 计算统计数据
        if latencies:
            avg_latency = statistics.mean(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0
        else:
            avg_latency = min_latency = max_latency = std_dev = 0

        success_rate = (success_count / count) * 100 if count > 0 else 0

        result = {
            "test_name": "多次连接稳定性测试",
            "success": success_count == count,
            "total_count": count,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "std_dev_ms": round(std_dev, 2),
            "latencies_ms": [round(l, 2) for l in latencies]
        }

        # 打印结果
        print("\n" + "-"*60)
        print(f"测试结果统计:")
        print(f"  总测试次数: {count}")
        print(f"  成功次数: {success_count}")
        print(f"  失败次数: {failure_count}")
        print(f"  成功率: {success_rate:.2f}%")
        print(f"  平均延迟: {avg_latency:.2f}ms")
        print(f"  最小延迟: {min_latency:.2f}ms")
        print(f"  最大延迟: {max_latency:.2f}ms")
        if len(latencies) > 1:
            print(f"  延迟标准差: {std_dev:.2f}ms")
        print("-"*60)

        self.test_results.append(result)
        return result

    async def test_concurrent_connections(self, count: int = 3) -> Dict[str, Any]:
        """测试并发连接稳定性"""
        print("\n" + "="*60)
        print(f"测试 3: 并发连接稳定性测试 ({count} 个并发)")
        print("="*60)

        async def single_connection_test(index: int) -> Dict[str, Any]:
            """单个连接测试"""
            try:
                start_time = time.time()
                access_token = await self.client._get_access_token()
                end_time = time.time()
                latency = (end_time - start_time) * 1000

                return {
                    "index": index,
                    "success": bool(access_token),
                    "latency_ms": round(latency, 2),
                    "error": None
                }
            except Exception as e:
                return {
                    "index": index,
                    "success": False,
                    "latency_ms": 0,
                    "error": str(e)
                }

        # 并发执行多个连接测试
        tasks = [single_connection_test(i+1) for i in range(count)]
        results = await asyncio.gather(*tasks)

        # 分析结果
        success_count = sum(1 for r in results if r["success"])
        failure_count = count - success_count
        success_rate = (success_count / count) * 100 if count > 0 else 0

        successful_latencies = [r["latency_ms"] for r in results if r["success"]]
        if successful_latencies:
            avg_latency = statistics.mean(successful_latencies)
            min_latency = min(successful_latencies)
            max_latency = max(successful_latencies)
        else:
            avg_latency = min_latency = max_latency = 0

        # 打印每个并发的结果
        for r in results:
            if r["success"]:
                print(f"  并发 {r['index']}: ✅ 成功，延迟: {r['latency_ms']:.2f}ms")
            else:
                print(f"  并发 {r['index']}: ❌ 失败: {r['error']}")

        # 打印统计结果
        print("\n" + "-"*60)
        print(f"并发测试结果统计:")
        print(f"  并发数: {count}")
        print(f"  成功数: {success_count}")
        print(f"  失败数: {failure_count}")
        print(f"  成功率: {success_rate:.2f}%")
        if successful_latencies:
            print(f"  平均延迟: {avg_latency:.2f}ms")
            print(f"  最小延迟: {min_latency:.2f}ms")
            print(f"  最大延迟: {max_latency:.2f}ms")
        print("-"*60)

        result = {
            "test_name": "并发连接稳定性测试",
            "success": success_count == count,
            "total_count": count,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "individual_results": results
        }

        self.test_results.append(result)
        return result

    async def test_api_endpoint_connection(self) -> Dict[str, Any]:
        """测试API端点连接（使用日历API作为测试点）"""
        print("\n" + "="*60)
        print("测试 4: API端点连接测试 (日历API)")
        print("="*60)

        try:
            start_time = time.time()
            # 尝试获取日历事件（即使没有权限也能测试连接）
            result = await self.client.get_calendar_events(
                calendar_id="primary",
                max_results=1
            )
            end_time = time.time()
            latency = (end_time - start_time) * 1000

            if result.get("success"):
                events = result.get("events", [])
                test_result = {
                    "test_name": "API端点连接测试",
                    "success": True,
                    "latency_ms": round(latency, 2),
                    "events_count": len(events),
                    "message": f"API连接成功，获取到 {len(events)} 个事件"
                }
                print(f"✅ API连接成功")
                print(f"   延迟: {latency:.2f}ms")
                print(f"   获取到 {len(events)} 个日历事件")
            else:
                # 可能是权限问题，但连接本身是成功的
                test_result = {
                    "test_name": "API端点连接测试",
                    "success": True,  # 连接成功，只是可能权限不足
                    "latency_ms": round(latency, 2),
                    "message": f"API连接成功，但可能权限不足"
                }
                print(f"⚠️  API连接成功，但可能权限不足")
                print(f"   延迟: {latency:.2f}ms")

        except Exception as e:
            test_result = {
                "test_name": "API端点连接测试",
                "success": False,
                "latency_ms": 0,
                "message": f"API连接异常: {str(e)}"
            }
            print(f"❌ API连接异常: {str(e)}")
            logger.error(f"API端点连接测试失败: {str(e)}", exc_info=True)

        self.test_results.append(test_result)
        return test_result

    async def test_network_connectivity(self) -> Dict[str, Any]:
        """测试网络连通性（ping飞书API服务器）"""
        print("\n" + "="*60)
        print("测试 5: 网络连通性测试")
        print("="*60)

        import httpx

        test_urls = [
            "https://open.feishu.cn",
            "https://www.feishu.cn",
            "https://api.minimaxi.com"  # 测试大模型API连接
        ]

        results = []

        for url in test_urls:
            try:
                print(f"\n  测试连接: {url}")
                start_time = time.time()

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)

                end_time = time.time()
                latency = (end_time - start_time) * 1000

                result = {
                    "url": url,
                    "success": response.status_code < 500,
                    "status_code": response.status_code,
                    "latency_ms": round(latency, 2),
                    "message": f"状态码: {response.status_code}, 延迟: {latency:.2f}ms"
                }

                if response.status_code < 400:
                    print(f"  ✅ 连接成功，状态码: {response.status_code}，延迟: {latency:.2f}ms")
                elif response.status_code < 500:
                    print(f"  ⚠️  连接成功但有客户端错误，状态码: {response.status_code}")
                else:
                    print(f"  ❌ 服务器错误，状态码: {response.status_code}")

            except httpx.TimeoutException:
                result = {
                    "url": url,
                    "success": False,
                    "status_code": None,
                    "latency_ms": 0,
                    "message": "连接超时"
                }
                print(f"  ❌ 连接超时")

            except Exception as e:
                result = {
                    "url": url,
                    "success": False,
                    "status_code": None,
                    "latency_ms": 0,
                    "message": f"连接异常: {str(e)}"
                }
                print(f"  ❌ 连接异常: {str(e)}")
                logger.error(f"网络连通性测试失败 ({url}): {str(e)}")

            results.append(result)

        # 统计整体结果
        all_success = all(r["success"] for r in results)
        success_count = sum(1 for r in results if r["success"])

        test_result = {
            "test_name": "网络连通性测试",
            "success": all_success,
            "total_count": len(test_urls),
            "success_count": success_count,
            "success_rate": round((success_count / len(test_urls)) * 100, 2) if test_urls else 0,
            "individual_results": results
        }

        self.test_results.append(test_result)
        return test_result

    def print_final_report(self):
        """打印最终测试报告"""
        print("\n" + "="*60)
        print("最终测试报告")
        print("="*60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.get("success", False))
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0

        print(f"\n测试概况:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过测试: {passed_tests}")
        print(f"  失败测试: {failed_tests}")
        print(f"  通过率: {pass_rate:.2f}%")

        print("\n详细测试结果:")
        for i, result in enumerate(self.test_results, 1):
            status = "✅ 通过" if result.get("success", False) else "❌ 失败"
            test_name = result.get("test_name", f"测试 {i}")
            print(f"\n  {i}. {test_name}: {status}")

            # 显示额外信息
            if "latency_ms" in result:
                print(f"     延迟: {result['latency_ms']}ms")
            if "success_rate" in result:
                print(f"     成功率: {result['success_rate']}%")
            if "message" in result:
                print(f"     信息: {result['message']}")

        # 总体评估
        print("\n" + "-"*60)
        if pass_rate == 100:
            print("✅ 连接稳定性测试全部通过！智能体与飞书服务器连接稳定。")
        elif pass_rate >= 80:
            print("⚠️  连接稳定性测试基本通过，但存在少量失败。建议检查网络状况。")
        else:
            print("❌ 连接稳定性测试存在较多失败。请检查：")
            print("   1. 网络连接是否正常")
            print("   2. 飞书服务是否可用")
            print("   3. .env 配置是否正确")
            print("   4. 查看日志获取详细错误信息")
        print("-"*60)

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "pass_rate": round(pass_rate, 2),
            "detailed_results": self.test_results
        }


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("飞书智能体 - 连接稳定性测试")
    print("="*60)

    # 初始化
    setup_logger()
    logger.info("开始连接稳定性测试")

    # 检查配置
    print(f"\n配置检查：")
    print(f"  FEISHU_APP_ID: {settings.FEISHU_APP_ID[:8]}..." if settings.FEISHU_APP_ID else "  FEISHU_APP_ID: 未配置")
    print(f"  FEISHU_APP_SECRET: {'已配置' if settings.FEISHU_APP_SECRET else '未配置'}")

    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        print("\n❌ 错误: 飞书应用配置缺失，请检查 .env 文件")
        return

    # 创建测试器
    tester = ConnectionStabilityTester()

    # 运行所有测试
    await tester.test_basic_connection()
    await tester.test_multiple_connections(count=5)
    await tester.test_concurrent_connections(count=3)
    await tester.test_api_endpoint_connection()
    await tester.test_network_connectivity()

    # 打印最终报告
    final_report = tester.print_final_report()

    # 记录日志
    logger.info(f"连接稳定性测试完成: 通过率 {final_report['pass_rate']}%")

    print("\n💡 提示：")
    print("   如果测试失败，请检查：")
    print("   1. 网络连接是否正常")
    print("   2. 飞书服务是否可用")
    print("   3. .env 文件中的配置是否正确")
    print("   4. 查看 logs/feishu_agent.log 获取详细错误信息")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n测试发生异常: {str(e)}")
        logger.error(f"测试异常: {str(e)}", exc_info=True)
