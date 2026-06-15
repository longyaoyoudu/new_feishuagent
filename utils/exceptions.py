class FeishuAgentError(Exception):
    """飞书智能体基础异常类"""
    def __init__(self, message: str = "飞书智能体发生错误"):
        self.message = message
        super().__init__(self.message)


class ConfigurationError(FeishuAgentError):
    """配置错误异常类"""
    def __init__(self, message: str = "配置错误"):
        self.message = message
        super().__init__(self.message)


class FeishuAPIError(FeishuAgentError):
    """飞书API调用错误异常类"""
    def __init__(self, message: str = "飞书API调用失败", code: int = -1):
        self.message = message
        self.code = code
        super().__init__(f"{message} (错误码: {code})")


class AuthorizationError(FeishuAgentError):
    """授权错误异常类"""
    def __init__(self, message: str = "授权失败"):
        self.message = message
        super().__init__(self.message)


class FunctionExecutionError(FeishuAgentError):
    """功能执行错误异常类"""
    def __init__(self, message: str = "功能执行失败", function_name: str = ""):
        self.message = message
        self.function_name = function_name
        super().__init__(f"函数 {function_name} 执行失败: {message}")


class ModelError(FeishuAgentError):
    """大模型调用错误异常类"""
    def __init__(self, message: str = "大模型调用失败", model_name: str = ""):
        self.message = message
        self.model_name = model_name
        super().__init__(f"模型 {model_name} 调用失败: {message}")
