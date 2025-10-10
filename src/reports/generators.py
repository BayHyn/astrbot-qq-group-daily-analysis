"""
报告生成器模块
负责生成各种格式的分析报告
"""

import base64
import aiohttp
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path
from astrbot.api import logger
from .templates import HTMLTemplates
from ..visualization.activity_charts import ActivityVisualizer
import asyncio


class ReportGenerator:
    """报告生成器"""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.activity_visualizer = ActivityVisualizer()

    async def generate_image_report(self, analysis_result: Dict, group_id: str, html_render_func) -> Optional[str]:
        """生成图片格式的分析报告"""
        try:
            # 准备渲染数据
            render_payload = await self._prepare_render_data(analysis_result)
            # 使用AstrBot内置的HTML渲染服务（直接传递模板和数据）
            # 使用兼容的图片生成选项（基于NetworkRenderStrategy的默认设置）
            image_options = {
                "full_page": True,
                "type": "jpeg",  # 使用默认的jpeg格式提高兼容性
                "quality": 95,   # 设置合理的质量
            }
            image_url = await html_render_func(
                HTMLTemplates.get_image_template(),
                render_payload,
                True,  # return_url=True，返回URL而不是下载文件
                image_options
            )

            logger.info(f"图片生成成功: {image_url}")
            return image_url

        except Exception as e:
            logger.error(f"生成图片报告失败: {e}", exc_info=True)
            # 尝试使用更简单的选项作为后备方案
            try:
                logger.info("尝试使用低质量选项重新生成...")
                simple_options = {
                    "full_page": True,
                    "type": "jpeg",
                    "quality": 70  # 降低质量以提高兼容性
                }
                image_url = await html_render_func(
                    HTMLTemplates.get_image_template(),
                    render_payload,
                    True,
                    simple_options
                )
                logger.info(f"使用低质量选项生成成功: {image_url}")
                return image_url
            except Exception as fallback_e:
                logger.error(f"后备低质量方案也失败: {fallback_e}")
                return None



    async def generate_pdf_report(self, analysis_result: Dict, group_id: str) -> Optional[str]:
        """生成PDF格式的分析报告"""
        try:
            # 确保输出目录存在
            output_dir = Path(self.config_manager.get_pdf_output_dir())
            output_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            current_date = datetime.now().strftime('%Y%m%d')
            filename = self.config_manager.get_pdf_filename_format().format(
                group_id=group_id,
                date=current_date
            )
            pdf_path = output_dir / filename

            # 准备渲染数据
            render_data = await self._prepare_render_data(analysis_result)
            logger.info(f"PDF 渲染数据准备完成，包含 {len(render_data)} 个字段")

            # 生成 HTML 内容（PDF模板使用{}占位符）
            html_content = self._render_html_template(HTMLTemplates.get_pdf_template(), render_data, use_jinja_style=False)
            logger.info(f"HTML 内容生成完成，长度: {len(html_content)} 字符")

            # 转换为 PDF
            success = await self._html_to_pdf(html_content, str(pdf_path))

            if success:
                return str(pdf_path.absolute())
            else:
                return None

        except Exception as e:
            logger.error(f"生成 PDF 报告失败: {e}")
            return None

    def generate_text_report(self, analysis_result: Dict) -> str:
        """生成文本格式的分析报告"""
        stats = analysis_result["statistics"]
        topics = analysis_result["topics"]
        user_titles = analysis_result["user_titles"]

        report = f"""
🎯 群聊日常分析报告
📅 {datetime.now().strftime('%Y年%m月%d日')}

📊 基础统计
• 消息总数: {stats.message_count}
• 参与人数: {stats.participant_count}
• 总字符数: {stats.total_characters}
• 表情数量: {stats.emoji_count}
• 最活跃时段: {stats.most_active_period}

💬 热门话题
"""

        max_topics = self.config_manager.get_max_topics()
        for i, topic in enumerate(topics[:max_topics], 1):
            contributors_str = "、".join(topic.contributors)
            report += f"{i}. {topic.topic}\n"
            report += f"   参与者: {contributors_str}\n"
            report += f"   {topic.detail}\n\n"

        report += "🏆 群友称号\n"
        max_user_titles = self.config_manager.get_max_user_titles()
        for title in user_titles[:max_user_titles]:
            report += f"• {title.name} - {title.title} ({title.mbti})\n"
            report += f"  {title.reason}\n\n"

        report += "💬 群圣经\n"
        max_golden_quotes = self.config_manager.get_max_golden_quotes()
        for i, quote in enumerate(stats.golden_quotes[:max_golden_quotes], 1):
            report += f"{i}. \"{quote.content}\" —— {quote.sender}\n"
            report += f"   {quote.reason}\n\n"

        return report

    async def _prepare_render_data(self, analysis_result: Dict) -> Dict:
        """准备渲染数据"""
        stats = analysis_result["statistics"]
        topics = analysis_result["topics"]
        user_titles = analysis_result["user_titles"]
        activity_viz = stats.activity_visualization

        # 构建话题HTML
        topics_html = ""
        max_topics = self.config_manager.get_max_topics()
        for i, topic in enumerate(topics[:max_topics], 1):
            contributors_str = "、".join(topic.contributors)
            topics_html += f"""
            <div class="topic-item">
                <div class="topic-header">
                    <span class="topic-number">{i}</span>
                    <span class="topic-title">{topic.topic}</span>
                </div>
                <div class="topic-contributors">参与者: {contributors_str}</div>
                <div class="topic-detail">{topic.detail}</div>
            </div>
            """

        # 构建用户称号HTML（包含头像）
        titles_html = ""
        max_user_titles = self.config_manager.get_max_user_titles()
        for title in user_titles[:max_user_titles]:
            # 获取用户头像
            avatar_data = await self._get_user_avatar(str(title.qq))
            avatar_html = f'<img src="{avatar_data}" class="user-avatar" alt="头像">' if avatar_data else '<div class="user-avatar-placeholder">👤</div>'

            titles_html += f"""
            <div class="user-title">
                <div class="user-info">
                    {avatar_html}
                    <div class="user-details">
                        <div class="user-name">{title.name}</div>
                        <div class="user-badges">
                            <div class="user-title-badge">{title.title}</div>
                            <div class="user-mbti">{title.mbti}</div>
                        </div>
                    </div>
                </div>
                <div class="user-reason">{title.reason}</div>
            </div>
            """

        # 构建金句HTML
        quotes_html = ""
        max_golden_quotes = self.config_manager.get_max_golden_quotes()
        for quote in stats.golden_quotes[:max_golden_quotes]:
            quotes_html += f"""
            <div class="quote-item">
                <div class="quote-content">"{quote.content}"</div>
                <div class="quote-author">—— {quote.sender}</div>
                <div class="quote-reason">{quote.reason}</div>
            </div>
            """

        # 生成活跃度可视化HTML
        hourly_chart_html = self.activity_visualizer.generate_hourly_chart_html(
            activity_viz.hourly_activity
        )

        # 返回扁平化的渲染数据
        return {
            "current_date": datetime.now().strftime('%Y年%m月%d日'),
            "current_datetime": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "message_count": stats.message_count,
            "participant_count": stats.participant_count,
            "total_characters": stats.total_characters,
            "emoji_count": stats.emoji_count,
            "most_active_period": stats.most_active_period,
            "topics_html": topics_html,
            "titles_html": titles_html,
            "quotes_html": quotes_html,
            "hourly_chart_html": hourly_chart_html,
            "total_tokens": stats.token_usage.total_tokens if stats.token_usage.total_tokens else 0,
            "prompt_tokens": stats.token_usage.prompt_tokens if stats.token_usage.prompt_tokens else 0,
            "completion_tokens": stats.token_usage.completion_tokens if stats.token_usage.completion_tokens else 0
        }




    def _render_html_template(self, template: str, data: Dict, use_jinja_style: bool = False) -> str:
        """HTML模板渲染，支持两种占位符格式

        Args:
            template: HTML模板字符串
            data: 渲染数据
            use_jinja_style: 是否使用Jinja2风格的{{ }}占位符，否则使用{}占位符
        """
        result = template

        # 调试：记录渲染数据
        logger.info(f"渲染数据键: {list(data.keys())}, 使用Jinja风格: {use_jinja_style}")

        for key, value in data.items():
            if use_jinja_style:
                # 图片模板使用{{ }}占位符
                placeholder = f"{{{{ {key} }}}}"
            else:
                # PDF模板使用{}占位符
                placeholder = f"{{{key}}}"

            # 调试：记录替换过程
            if placeholder in result:
                logger.debug(f"替换 {placeholder} -> {str(value)[:100]}...")
            result = result.replace(placeholder, str(value))

        # 检查是否还有未替换的占位符
        import re
        if use_jinja_style:
            remaining_placeholders = re.findall(r'\{\{[^}]+\}\}', result)
        else:
            remaining_placeholders = re.findall(r'\{[^}]+\}', result)

        if remaining_placeholders:
            logger.warning(f"未替换的占位符: {remaining_placeholders[:10]}")

        return result

    async def _get_user_avatar(self, user_id: str) -> Optional[str]:
        """获取用户头像的base64编码"""
        try:
            avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
            async with aiohttp.ClientSession() as client:
                response = await client.get(avatar_url)
                response.raise_for_status()
                avatar_data = await response.read()
                # 转换为base64编码
                avatar_base64 = base64.b64encode(avatar_data).decode('utf-8')
                return f"data:image/jpeg;base64,{avatar_base64}"
        except Exception as e:
            logger.error(f"获取用户头像失败 {user_id}: {e}")
            return None

    async def _html_to_pdf(self, html_content: str, output_path: str) -> bool:
        """将 HTML 内容转换为 PDF 文件"""
        try:
            # 确保 pyppeteer 可用
            if not self.config_manager.pyppeteer_available:
                logger.error("pyppeteer 不可用，无法生成 PDF")
                return False

            # 动态导入 pyppeteer
            import pyppeteer
            from pyppeteer import launch
            import sys
            import os

            # 尝试启动浏览器，如果 Chromium 不存在会自动下载
            logger.info("启动浏览器进行 PDF 转换")

            # 配置浏览器启动参数，解决Docker环境中的沙盒问题
            launch_options = {
                'headless': True,
                'args': [
                    '--no-sandbox',  # Docker环境必需 - 禁用沙盒
                    '--disable-setuid-sandbox',  # Docker环境必需 - 禁用setuid沙盒
                    '--disable-dev-shm-usage',  # 避免共享内存问题
                    '--disable-gpu',  # 禁用GPU加速
                    '--no-first-run',
                    '--disable-extensions',
                    '--disable-default-apps',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--disable-background-networking',
                    '--enable-features=NetworkService,NetworkServiceInProcess',
                    '--force-color-profile=srgb',
                    '--metrics-recording-only',
                    '--disable-breakpad',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-features=Translate,BackForwardCache,AcceptCHFrame,AvoidUnnecessaryBeforeUnloadCheckSync',
                    '--enable-automation',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    '--export-tagged-pdf',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-blink-features=AutomationControlled',  # 隐藏自动化特征
                ]
            }

            # 检测系统 Chrome/Chromium 路径
            chrome_paths = []
            
            if sys.platform.startswith('win'):
                # Windows 系统 Chrome 安装路径
                username = os.environ.get('USERNAME', '')
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    rf"C:\Users\{username}\AppData\Local\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files\Chromium\Application\chrome.exe",
                ]
            elif sys.platform.startswith('linux'):
                # Linux 系统 Chrome/Chromium 路径
                chrome_paths = [
                    '/usr/bin/google-chrome',
                    '/usr/bin/google-chrome-stable',
                    '/usr/bin/chromium',
                    '/usr/bin/chromium-browser',
                    '/snap/bin/chromium',
                    '/usr/bin/chromium-freeworld',
                ]
            elif sys.platform.startswith('darwin'):
                # macOS 系统 Chrome 路径
                chrome_paths = [
                    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                    '/Applications/Chromium.app/Contents/MacOS/Chromium',
                ]

            # 查找可用的浏览器
            found_browser = False
            for chrome_path in chrome_paths:
                if Path(chrome_path).exists():
                    launch_options['executablePath'] = chrome_path
                    logger.info(f"使用系统浏览器: {chrome_path}")
                    found_browser = True
                    break
            
            if not found_browser:
                logger.info("未找到系统浏览器，将使用 pyppeteer 默认下载的 Chromium")
                # 先尝试确保 Chromium 已下载
                try:
                    from pyppeteer import connection, browser, launcher
                    launcher_instance = launcher.Launcher(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                    )
                    await launcher_instance._get_chromium_revision()
                    await launcher_instance._download_chromium()
                    chromium_path = pyppeteer.executablePath()
                    launch_options['executablePath'] = chromium_path
                    logger.info(f"使用 pyppeteer 下载的 Chromium: {chromium_path}")
                except Exception as pre_download_err:
                    logger.warning(f"预下载 Chromium 失败，继续尝试直接启动: {pre_download_err}")

            # 尝试启动浏览器
            try:
                logger.info("正在启动浏览器...")
                browser = await launch(**launch_options)
                logger.info("浏览器启动成功")
            except Exception as e:
                logger.error(f"浏览器启动失败: {e}", exc_info=True)
                return False

            try:
                # 创建新页面，设置更合理的超时时间
                page = await browser.newPage()
                
                # 设置页面视口，减少内存占用
                await page.setViewport({
                    'width': 1024,
                    'height': 768,
                    'deviceScaleFactor': 1,
                    'isMobile': False,
                    'hasTouch': False,
                    'isLandscape': False
                })

                # 设置页面内容，使用更安全的加载方式
                logger.info("开始设置页面内容...")
                await page.setContent(html_content, {'waitUntil': 'domcontentloaded', 'timeout': 30000})
                
                # 等待页面基本加载完成，但不要太长时间
                try:
                    await page.waitForSelector('body', {'timeout': 5000})
                    logger.info("页面基本加载完成")
                except Exception:
                    logger.warning("等待页面加载超时，继续执行")
                
                # 减少等待时间，避免内存累积
                await asyncio.sleep(1)

                # 导出 PDF，使用更保守的设置
                logger.info("开始生成PDF...")
                pdf_options = {
                    'path': output_path,
                    'format': 'A4',
                    'printBackground': True,
                    'margin': {
                        'top': '10mm',
                        'right': '10mm',
                        'bottom': '10mm',
                        'left': '10mm'
                    },
                    'scale': 0.8,
                    'displayHeaderFooter': False,
                    'preferCSSPageSize': True,
                    'timeout': 60000  # 增加PDF生成超时时间到60秒
                }
                
                await page.pdf(pdf_options)
                logger.info(f"PDF 生成成功: {output_path}")
                return True

            except Exception as e:
                logger.error(f"PDF生成过程中出错: {e}")
                return False
                
            finally:
                # 确保浏览器被正确关闭
                if browser:
                    try:
                        logger.info("正在关闭浏览器...")
                        # 先关闭所有页面
                        pages = await browser.pages()
                        for page in pages:
                            try:
                                await page.close()
                            except:
                                pass
                        
                        # 等待一小段时间让资源释放
                        await asyncio.sleep(0.5)
                        
                        # 关闭浏览器
                        await browser.close()
                        logger.info("浏览器已关闭")
                    except Exception as e:
                        logger.warning(f"关闭浏览器时出错: {e}")
                        # 强制清理
                        try:
                            await browser.disconnect()
                        except:
                            pass

        except Exception as e:
            error_msg = str(e)
            if "Chromium downloadable not found" in error_msg:
                logger.error("Chromium 下载失败，建议安装系统 Chrome/Chromium")
                logger.info("💡 Linux 系统建议: sudo apt-get install chromium-browser 或 sudo yum install chromium")
            elif "No usable sandbox" in error_msg:
                logger.error("沙盒权限问题，已尝试禁用沙盒")
            elif "Connection refused" in error_msg or "connect" in error_msg.lower():
                logger.error("浏览器连接失败，请检查系统资源或尝试重启")
            elif "executablePath" in error_msg and "not found" in error_msg:
                logger.error("未找到系统浏览器，请安装 Chrome 或 Chromium")
                logger.info("💡 安装建议: sudo apt-get install chromium-browser (Ubuntu/Debian) 或 sudo yum install chromium (CentOS/RHEL)")
            elif "Browser closed unexpectedly" in error_msg:
                logger.error("浏览器意外关闭，可能是由于内存不足或系统资源限制")
                logger.info("💡 建议: 检查系统内存，或重启 AstrBot 后重试")
                logger.info("💡 如果问题持续，可以尝试以下解决方案:")
                logger.info("   1. 增加系统交换空间")
                logger.info("   2. 使用更简单的浏览器启动参数")
                logger.info("   3. 考虑使用其他 PDF 生成方案")
            else:
                logger.error(f"HTML 转 PDF 失败: {e}")
                logger.info("💡 可以尝试使用 /安装PDF 命令重新安装依赖，或检查系统日志获取更多信息")
            return False