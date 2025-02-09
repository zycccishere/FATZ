import tkinter as tk
from tkinter import ttk
import threading
import itertools
from playwright.sync_api import sync_playwright
import os
import time
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import convertapi
from pyzotero import zotero
import json
from pathlib import Path

class State:
    idle = "idle"
    saving = "saving"
    importing = "importing"


class InputWindow:
    # 定义界面常量
    TITLE_FONT_SIZE = 24
    INPUT_FONT_SIZE = 22
    BUTTON_UNPRESSED_SIZE = 40
    BUTTON_SHRINK = 4
    DISPLAY_FONT_SIZE = 14
    INPUT_HEIGHT = 12  # 输入框和按钮的统一高度
    LOADING_DOTS = ["   ", ".  ", ".. ", "..."]  # 加载动画的点

    fetching_index = None
    title = None
    success_save = False

    state = State.idle
    loading_animation = None  # 用于存储动画定时器ID

    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.root.title("From arXiv to Zotero")
        self.zot = zotero.Zotero(
            config["zotero"]["library_id"],
            "user",
            config["zotero"]["api_key"],
        )
        # 设置默认窗口大小为 600x300，并使窗口在屏幕中央显示
        window_width = 600
        window_height = 300
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int((screen_width - window_width) / 2)
        center_y = int((screen_height - window_height) / 2)
        self.root.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")

        # 配置根窗口的网格权重
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 创建主框架
        self.main_frame = ttk.Frame(self.root, padding="20")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置主框架的网格权重
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=3)
        self.main_frame.grid_columnconfigure(1, weight=1)

        # 创建标题标签
        self.title_label = ttk.Label(
            self.main_frame,
            text="请输入arXiv论文的编号\n    (eg. 2402.00001)",
            font=("Helvetica", self.TITLE_FONT_SIZE, "bold"),
        )
        self.title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))

        # 创建输入框容器
        self.input_frame = ttk.Frame(self.main_frame)
        self.input_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_columnconfigure(1, weight=0)  # 按钮列不伸缩

        # 创建输入框
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(
            self.input_frame,
            textvariable=self.input_var,
            font=("Helvetica", self.INPUT_FONT_SIZE),
            style="Large.TEntry",
        )
        self.input_entry.grid(
            row=0, column=0, padx=(10, 5), ipady=self.INPUT_HEIGHT, sticky=(tk.W, tk.E)
        )
        # 绑定回车键事件
        self.input_entry.bind("<Return>", lambda event: self.save_submit())

        # 创建转存按钮容器（用于固定按钮大小）
        save_button_size = 50  # 按钮容器的固定尺寸
        self.save_button_frame = ttk.Frame(
            self.input_frame, width=save_button_size, height=save_button_size
        )  # 固定宽度和高度
        self.save_button_frame.grid(row=0, column=1, padx=(0, 5))
        self.save_button_frame.grid_propagate(False)  # 防止框架大小随内容变化

        # 创建转存按钮（使用Label实现）
        self.save_button = tk.Label(
            self.save_button_frame,
            text="✅",
            font=("Helvetica", self.BUTTON_UNPRESSED_SIZE),
            cursor="hand2",
        )
        self.save_button.place(relx=0.5, rely=0.5, anchor="center")

        # 绑定点击和悬停事件
        self.save_button.bind("<Button-1>", self.on_save_button_press)  # 鼠标按下
        self.save_button.bind(
            "<ButtonRelease-1>", self.on_save_button_release
        )  # 鼠标释放

        # 创建显示标签
        self.display_label = ttk.Label(
            self.main_frame,
            text="",
            font=("Helvetica", self.DISPLAY_FONT_SIZE),
            wraplength=450,
        )
        self.display_label.grid(
            row=2, column=0, columnspan=2, pady=(10, 5), sticky=(tk.W, tk.E)
        )

        # 创建导入按钮容器
        self.import_button_frame = ttk.Frame(self.main_frame)
        self.import_button_frame.grid(
            row=3, column=0, columnspan=2, pady=(5, 10), sticky=(tk.W, tk.E)
        )
        self.import_button_frame.grid_columnconfigure(0, weight=1)

        # 创建导入按钮
        self.import_button = ttk.Button(
            self.import_button_frame,
            text="Import to Zotero",
            padding=(20, 10),  # 添加内边距使按钮更高
            style="Import.TButton",
        )
        self.import_button.grid(row=0, column=0)  # 使用grid而不是place

        # 绑定导入按钮点击事件
        self.import_button.bind("<Button-1>", self.import_submit)

    def on_save_button_press(self, event):
        """按钮按下效果"""
        self.save_button.configure(
            font=(
                "Helvetica",
                self.BUTTON_UNPRESSED_SIZE - self.BUTTON_SHRINK,
            ),  # 减小字体大小
        )
        # 向下移动2像素
        self.save_button.place_configure(rely=0.52)  # 稍微向下移动

    def on_save_button_release(self, event):
        """按钮释放效果并提交"""
        self.save_button.configure(
            font=("Helvetica", self.BUTTON_UNPRESSED_SIZE),  # 恢复原始大小
        )
        # 恢复原始位置
        self.save_button.place_configure(rely=0.5)
        self.save_submit()

    def lock_interface(self):
        """锁定界面"""
        self.input_entry.configure(state="disabled")  # 禁用输入框
        self.save_button.configure(cursor="watch")  # 改变鼠标样式为等待
        self.save_button.unbind("<Button-1>")  # 移除点击事件
        self.save_button.unbind("<ButtonRelease-1>")
        self.input_entry.unbind("<Return>")  # 移除回车事件
        # 禁用导入按钮
        self.import_button.configure(state="disabled")

    def start_loading_animation(self):
        """开始加载动画"""
        if self.loading_animation is not None:
            return

        dots_cycle = itertools.cycle(self.LOADING_DOTS)

        def update_dots():
            if not self.state == State.saving:
                self.loading_animation = None
                return
            dots = next(dots_cycle)
            if self.state == State.saving:
                if self.title is None:
                    self.display_label.config(text=f"       正在获取网页{dots}")
                else:
                    self.display_label.config(
                        text=f"       正在翻译并转存： {self.title}{dots}"
                    )
            elif self.state == State.importing:
                self.display_label.config(text=f"       正在导入： {dots}")
            self.loading_animation = self.root.after(300, update_dots)

        update_dots()

    def stop_loading_animation(self):
        """停止加载动画"""
        if self.loading_animation is not None:
            self.root.after_cancel(self.loading_animation)
            self.loading_animation = None

    def import_in_thread(self):
        """在新线程中处理导入"""
        try:
            self.upload_pdf_to_zotero()
            self.root.after(
                0,
                lambda: self.display_label.config(
                    text=f"       {self.title} 已成功导入Zotero"
                ),
            )
        except Exception as e:
            self.root.after(
                0,
                lambda: self.display_label.config(
                    text=f"       {self.title} 导入Zotero失败：{e}"
                ),
            )
        finally:
            self.root.after(0, self.unlock_interface)
            self.root.after(0, self.unlock_import_interface)
            self.state = State.idle
            self.success_save = False

    def save_in_thread(self):
        """在新线程中处理翻译和保存"""
        try:
            self.translate_and_save()
            self.success_save = True
            self.root.after(
                0,
                lambda: self.display_label.config(
                    text=f"       {self.title} 已成功转存"
                ),
            )
            self.root.after(0, self.unlock_import_interface)
        except Exception as e:
            self.success_save = False
            self.root.after(
                0,
                lambda: self.display_label.config(
                    text=f"       {self.title} 翻译并转存失败：{e}"
                ),
            )
            self.root.after(0, self.lock_import_interface)
        finally:
            self.root.after(0, self.unlock_interface)

    def save_submit(self):
        # 如果已经锁定，直接返回
        if not (self.state == State.idle):
            return

        # 获取输入内容并更新显示标签
        input_text = self.input_var.get()
        if input_text.strip():  # 检查是否为空
            self.title = None
            self.input_var.set("")  # 清空输入框
            self.state = State.saving
            self.lock_import_interface()
            self.lock_interface()  # 锁定界面
            self.fetching_index = input_text

            # 开始加载动画
            self.start_loading_animation()

            # 在新线程中处理
            thread = threading.Thread(target=self.save_in_thread)
            thread.daemon = True  # 设置为守护线程
            thread.start()

        self.input_entry.focus()  # 将焦点返回到输入框

    def import_submit(self, event):
        """导入按钮提交"""
        if not (self.success_save and self.state == State.idle):
            return

        # 更新状态
        self.state = State.importing
        self.import_button.configure(state="pressed")
        self.lock_interface()

        # 开始加载动画
        self.start_loading_animation()

        # 在新线程中处理
        thread = threading.Thread(target=self.import_in_thread)
        thread.daemon = True  # 设置为守护线程
        thread.start()

        self.input_entry.focus()  # 将焦点返回到输入框

    def unlock_interface(self):
        """解锁界面"""
        self.stop_loading_animation()  # 停止加载动画
        self.input_entry.configure(state="normal")  # 启用输入框
        self.save_button.configure(cursor="hand2")  # 恢复鼠标样式
        self.save_button.bind(
            "<Button-1>", self.on_save_button_press
        )  # 重新绑定点击事件
        self.save_button.bind("<ButtonRelease-1>", self.on_save_button_release)
        self.input_entry.bind(
            "<Return>", lambda event: self.save_submit()
        )  # 重新绑定回车事件
        self.state = State.idle

    def unlock_import_interface(self):
        """解锁导入按钮"""
        self.import_button.configure(state="normal")

    def lock_import_interface(self):
        """锁定导入按钮"""
        self.import_button.configure(state="disabled")

    def translate_and_save(self):
        """翻译并保存"""
        translated_webpage = self.export_translated_html()
        converted_webpage = self.convert_paths_to_absolute(
            translated_webpage, "https://ar5iv.labs.arxiv.org"
        )
        with open("converted_webpage.html", "w", encoding="utf-8") as f:
            f.write(converted_webpage)

        convertapi.api_credentials = self.config["convertapi"]["api_credentials"]
        convertapi.convert(
            "pdf", {"File": "converted_webpage.html"}, from_format="html"
        ).save_files(f"{self.title}.pdf")

    def validate_extension_path(self, path):
        """扩展路径验证函数"""
        required_files = ["manifest.json", "background.js"]
        for f in required_files:
            if not os.path.exists(os.path.join(path, f)):
                raise FileNotFoundError(f"扩展目录缺少必要文件: {f}")

    def export_translated_html(
        self, extension_id="bpoadfkcbjbfhfodiogcnhhhpibjhbnh", version="1.13.8_0"
    ):

        extension_path = os.path.abspath(
            os.path.expanduser(
                f"~/Library/Application Support/Google/Chrome/Default/Extensions/{extension_id}/{version}"
            )
        )

        self.validate_extension_path(extension_path)

        with sync_playwright() as p:
            # 配置参数
            user_data_dir = "./chrome_profile"  # 持久化用户数据存储目录

            # 启动带扩展的浏览器实例
            browser = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,  # 保持有头模式以确保扩展正常工作
                no_viewport=True,  # 禁用viewport自动调整
                args=[
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-position=-10000,-10000",  # 将窗口移到屏幕外
                    "--window-size=1,1",  # 设置窗口大小为最小
                ],
                viewport=None,  # 移除viewport设置
            )

            page = browser.new_page()

            # 使用多个方法来确保窗口不可见
            page.evaluate(
                """() => {
                window.moveTo(-10000, -10000);
                window.resizeTo(1, 1);
                document.documentElement.style.display = 'none';
            }"""
            )

            # 访问目标论文地址
            target_url = f"https://ar5iv.labs.arxiv.org/html/{self.fetching_index}?_immersive_translate_auto_translate=1"
            page.goto(target_url, wait_until="networkidle")

            self.title = page.title()
            self.title = self.title.split("]")[-1].strip()

            # 执行页面滚动，触发懒加载内容
            page.evaluate(
                """async () => {
                await new Promise(resolve => {
                    let totalHeight = 0;
                    const distance = 100;
                    const timer = setInterval(() => {
                        const scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        
                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                            window.scrollTo(0, 0);  // 滚回顶部
                            resolve();
                        }
                    },400);
                });
            }"""
            )

            # 再次等待网络空闲，确保懒加载内容已加载
            page.wait_for_load_state("networkidle")

            # 等待可能的动态渲染完成
            time.sleep(2)

            # 获取完整HTML内容
            translated_html = page.content()

            browser.close()

            return translated_html

    def convert_paths_to_absolute(self, html_content, base_url):
        """将HTML中的相对路径转换为绝对URL"""

        # 解析HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # 需要处理的标签和属性
        tag_attributes = {
            "img": ["src", "data-src"],
            "link": ["href"],
            "script": ["src"],
            "a": ["href"],
            "video": ["src", "poster"],
            "source": ["src", "srcset"],
            "meta": ["content"],  # 针对 og:image 等元标签
        }

        # 处理所有指定的标签和属性
        for tag, attributes in tag_attributes.items():
            for element in soup.find_all(tag):
                for attr in attributes:
                    if element.get(attr):
                        # 处理srcset属性（常见于responsive images）
                        if attr == "srcset":
                            srcset_urls = element[attr].split(",")
                            new_srcset_parts = []
                            for part in srcset_urls:
                                url, *size = part.strip().split()
                                absolute_url = urljoin(base_url, url)
                                new_srcset_parts.append(
                                    f"{absolute_url} {' '.join(size)}"
                                )
                            element[attr] = ", ".join(new_srcset_parts)
                        # 处理普通URL
                        else:
                            url = element[attr]
                            # 跳过数据URL和javascript
                            if not url.startswith(
                                ("data:", "javascript:", "mailto:", "tel:")
                            ):
                                element[attr] = urljoin(base_url, url)

        # 处理CSS中的URL（如background-image）
        style_tags = soup.find_all("style")
        for style in style_tags:
            if style.string:
                # 使用正则表达式查找CSS中的URL
                urls = re.findall(r'url\([\'"]?([^\'"())]+)[\'"]?\)', style.string)
                for url in urls:
                    if not url.startswith(("data:", "http://", "https://")):
                        absolute_url = urljoin(base_url, url)
                        style.string = style.string.replace(
                            f"url({url})", f"url({absolute_url})"
                        )

        # 处理内联样式
        elements_with_style = soup.find_all(attrs={"style": True})
        for element in elements_with_style:
            style = element["style"]
            urls = re.findall(r'url\([\'"]?([^\'"())]+)[\'"]?\)', style)
            for url in urls:
                if not url.startswith(("data:", "http://", "https://")):
                    absolute_url = urljoin(base_url, url)
                    element["style"] = style.replace(
                        f"url({url})", f"url({absolute_url})"
                    )

        return str(soup)

    def upload_pdf_to_zotero(self):

        try:
            # 检查PDF文件是否存在
            if not Path(f"{self.title}.pdf").exists():
                raise FileNotFoundError(f"PDF文件不存在：{f'{self.title}.pdf'}")

            # 从文件名中提取标题
            title = self.title

            # 创建文献条目
            template = self.zot.item_template("preprint")
            template["title"] = title
            template["archiveID"] = f"arXiv:{self.fetching_index}"
            # 创建条目
            resp = self.zot.create_items([template])

            if resp.get("successful"):
                # 获取创建的条目的key
                item_key = resp["successful"]["0"]["key"]

                # 上传PDF附件
                self.zot.attachment_simple([f"{self.title}.pdf"], item_key)

            else:
                raise Exception("创建条目失败")

        except Exception as e:
            raise Exception(f"上传过程中出错：{e}")


def main():
    with open("config.json", "r") as f:
        config = json.load(f)
    root = tk.Tk()
    # 设置最小窗口大小
    root.minsize(500, 250)
    app = InputWindow(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()
