"""
数据模型定义
包含所有分析相关的数据结构
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class SummaryTopic:
    """话题总结数据结构"""
    topic: str
    contributors: List[str]
    detail: str


@dataclass
class UserTitle:
    """用户称号数据结构"""
    name: str
    qq: int
    title: str
    mbti: str
    reason: str


@dataclass
class GoldenQuote:
    """群聊金句数据结构"""
    content: str
    sender: str
    reason: str


@dataclass
class TokenUsage:
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class EmojiStatistics:
    """表情统计数据结构"""
    face_count: int = 0  # QQ基础表情数量
    mface_count: int = 0  # 动画表情数量
    bface_count: int = 0  # 超级表情数量
    sface_count: int = 0  # 小表情数量
    other_emoji_count: int = 0  # 其他表情数量
    face_details: dict = field(default_factory=dict)  # 具体表情ID统计 {face_id: count}

    @property
    def total_emoji_count(self) -> int:
        """总表情数量"""
        return self.face_count + self.mface_count + self.bface_count + self.sface_count + self.other_emoji_count


@dataclass
class GroupStatistics:
    """群聊统计数据结构"""
    message_count: int
    total_characters: int
    participant_count: int
    most_active_period: str
    golden_quotes: List[GoldenQuote]
    emoji_count: int  # 保持向后兼容
    emoji_statistics: EmojiStatistics = field(default_factory=EmojiStatistics)
    token_usage: TokenUsage = field(default_factory=TokenUsage)