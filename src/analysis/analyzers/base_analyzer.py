"""
基础分析器抽象类
定义通用分析流程和接口
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Any, Optional
from datetime import datetime
from astrbot.api import logger
from ...models.data_models import TokenUsage
from ..utils.json_utils import parse_json_response
from ..utils.llm_utils import call_provider_with_retry, extract_token_usage, extract_response_text
import re

class BaseAnalyzer(ABC):
    """
    基础分析器抽象类
    定义所有分析器的通用接口和流程
    """
    
    def __init__(self, context, config_manager):
        """
        初始化基础分析器
        
        Args:
            context: AstrBot上下文对象
            config_manager: 配置管理器
        """
        self.context = context
        self.config_manager = config_manager
    
    @abstractmethod
    def get_data_type(self) -> str:
        """
        获取数据类型标识
        
        Returns:
            数据类型字符串
        """
        pass
    
    @abstractmethod
    def get_max_count(self) -> int:
        """
        获取最大提取数量
        
        Returns:
            最大数量
        """
        pass
    
    @abstractmethod
    def build_prompt(self, data: Any) -> str:
        """
        构建LLM提示词
        
        Args:
            data: 输入数据
            
        Returns:
            提示词字符串
        """
        pass
    
    @abstractmethod
    def extract_with_regex(self, result_text: str, max_count: int) -> List[Dict]:
        """
        使用正则表达式提取数据
        
        Args:
            result_text: LLM响应文本
            max_count: 最大提取数量
            
        Returns:
            提取到的数据列表
        """
        pass
    
    @abstractmethod
    def create_data_objects(self, data_list: List[Dict]) -> List[Any]:
        """
        创建数据对象列表
        
        Args:
            data_list: 原始数据列表
            
        Returns:
            数据对象列表
        """
        pass
    
    async def analyze(self, data: Any, umo: str = None) -> Tuple[List[Any], TokenUsage]:
        """
        统一的分析流程
        
        Args:
            data: 输入数据
            umo: 模型唯一标识符
            
        Returns:
            (分析结果列表, Token使用统计)
        """
        try:
            # 1. 构建提示词
            prompt = self.build_prompt(data)
            logger.info(f"开始{self.get_data_type()}分析，构建提示词完成")
            
            # 2. 调用LLM
            max_tokens = self.get_max_tokens()
            temperature = self.get_temperature()
            
            response = await call_provider_with_retry(
                self.context, self.config_manager, prompt, 
                max_tokens, temperature, umo
            )
            
            if response is None:
                logger.error(f"{self.get_data_type()}分析调用LLM失败: provider返回None（重试失败）")
                return [], TokenUsage()
            
            # 3. 提取token使用统计
            token_usage_dict = extract_token_usage(response)
            token_usage = TokenUsage(
                prompt_tokens=token_usage_dict["prompt_tokens"],
                completion_tokens=token_usage_dict["completion_tokens"],
                total_tokens=token_usage_dict["total_tokens"]
            )
            
            # 4. 提取响应文本
            result_text = extract_response_text(response)
            logger.debug(f"{self.get_data_type()}分析原始响应: {result_text[:500]}...")
            
            # 5. 尝试JSON解析
            success, parsed_data, error_msg = parse_json_response(result_text, self.get_data_type())
            
            if success and parsed_data:
                # JSON解析成功，创建数据对象
                data_objects = self.create_data_objects(parsed_data)
                logger.info(f"{self.get_data_type()}分析成功，解析到 {len(data_objects)} 条数据")
                return data_objects, token_usage
            
            # 6. JSON解析失败，使用正则表达式降级
            logger.warning(f"{self.get_data_type()}JSON解析失败，尝试正则表达式提取: {error_msg}")
            regex_data = self.extract_with_regex(result_text, self.get_max_count())
            
            if regex_data:
                logger.info(f"{self.get_data_type()}正则表达式提取成功，获得 {len(regex_data)} 条数据")
                data_objects = self.create_data_objects(regex_data)
                return data_objects, token_usage
            else:
                # 最后的降级方案
                logger.warning(f"{self.get_data_type()}正则表达式提取失败，返回空列表")
                return [], token_usage
                
        except Exception as e:
            logger.error(f"{self.get_data_type()}分析失败: {e}")
            return [], TokenUsage()
    
    def get_max_tokens(self) -> int:
        """
        获取最大token数，子类可重写
        
        Returns:
            最大token数
        """
        return 10000
    
    def get_temperature(self) -> float:
        """
        获取温度参数，子类可重写
        
        Returns:
            温度参数
        """
        return 0.6
    
    