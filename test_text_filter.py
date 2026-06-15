import sys
sys.path.insert(0, '.')

from utils import remove_think_content, clean_model_output


def test_remove_think_content():
    test_cases = [
        {
            "input": "<think>我需要思考一下这个问题的答案</think>这是最终的回答",
            "expected": "这是最终的回答",
            "description": "基本的思考内容过滤"
        },
        {
            "input": "前面的内容<think>思考过程</think>后面的内容",
            "expected": "前面的内容后面的内容",
            "description": "中间的思考内容过滤"
        },
        {
            "input": "<think>第一行思考\n第二行思考</think>这是回答",
            "expected": "这是回答",
            "description": "多行思考内容过滤"
        },
        {
            "input": "<think>思考1</think>回答部分<think>思考2</think>更多回答",
            "expected": "回答部分更多回答",
            "description": "多个思考标签"
        },
        {
            "input": "这是没有思考标签的回答",
            "expected": "这是没有思考标签的回答",
            "description": "没有思考标签的情况"
        },
        {
            "input": "",
            "expected": "",
            "description": "空字符串"
        },
        {
            "input": "<think></think>",
            "expected": "",
            "description": "空的思考标签"
        },
    ]

    print("=== 测试 remove_think_content 函数 ===")
    all_passed = True
    for i, test in enumerate(test_cases, 1):
        result = remove_think_content(test["input"])
        # 处理可能的换行差异
        result = ' '.join(result.split())
        expected = ' '.join(test["expected"].split())
        
        if result == expected:
            print(f"✅ 测试 {i} 通过: {test['description']}")
        else:
            print(f"❌ 测试 {i} 失败: {test['description']}")
            print(f"   输入: {repr(test['input'])}")
            print(f"   期望: {repr(test['expected'])}")
            print(f"   实际: {repr(result)}")
            all_passed = False

    return all_passed


def test_clean_model_output():
    test_cases = [
        {
            "input": "<think>思考内容</think>   多余的空格   回答",
            "expected": "多余的空格 回答",
            "description": "清理多余空格"
        },
        {
            "input": "<think>思考</think>回答\n\n\n\n继续回答",
            "expected": "回答\n\n继续回答",
            "description": "清理多余换行"
        },
        {
            "input": ''' <think>The user is saying "你好" (hello). According to my instructions, when someone greets me, I should respond warmly and enthusiastically, not just ask "what can I help you with." I should be friendly and natural like a friend. 
 
 Let me respond in a warm, friendly way.</think> 
 
 你好呀！👋✨ 
 
 很高兴见到你！今天过得怎么样？😊 
 
 有什么我可以帮你的，或者想聊的吗？''',
            "expected": "你好呀！👋✨\n\n很高兴见到你！今天过得怎么样？😊\n\n有什么我可以帮你的，或者想聊的吗？",
            "description": "用户实际案例：英文思考内容+中文回答"
        },
        {
            "input": "<Think>大小写变体测试</Think>回答内容",
            "expected": "回答内容",
            "description": "大小写变体标签过滤"
        },
        {
            "input": "< think >带空格的标签</ think >回答内容",
            "expected": "回答内容",
            "description": "带空格的标签过滤"
        },
    ]

    print("\n=== 测试 clean_model_output 函数 ===")
    all_passed = True
    for i, test in enumerate(test_cases, 1):
        result = clean_model_output(test["input"])
        
        if result == test["expected"]:
            print(f"✅ 测试 {i} 通过: {test['description']}")
        else:
            print(f"❌ 测试 {i} 失败: {test['description']}")
            print(f"   输入: {repr(test['input'])}")
            print(f"   期望: {repr(test['expected'])}")
            print(f"   实际: {repr(result)}")
            all_passed = False

    return all_passed


if __name__ == "__main__":
    success1 = test_remove_think_content()
    success2 = test_clean_model_output()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败！")
