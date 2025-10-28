# === 在文件最顶部添加以下修复代码 ===
import sys
import os
# 修复：防止 sys.stdout / sys.stderr 为 None（常见于 PyInstaller --noconsole）
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
# === 然后再导入其他模块 ===
import flet as ft
import requests
import base64
import json
import csv
import time
import logging
import shutil
import zipfile
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import wraps
# === 加密相关导入 ===
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
# === HTTP服务器相关导入 ===
import threading
from download_server import DownloadServer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fofa_gui.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局下载服务器实例
download_server = DownloadServer()

# === 加密配置（请务必修改 SALT 和 PASSWORD 为自己的随机值）===
SALT = b'\x12\x34\x76\x78\x90\xab\xcd\xef\x72\x34\x56\x78\x90\xab\xcd\xef'  # 16字节
PASSWORD = b'my_secret_password_for_fofa_key_2025'  # 建议修改为强密码

def _derive_key(password: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password))

def encrypt_data(data: str) -> bytes:
    key = _derive_key(PASSWORD, SALT)
    f = Fernet(key)
    return f.encrypt(data.encode('utf-8'))

def decrypt_data(encrypted_data: bytes) -> str:
    key = _derive_key(PASSWORD, SALT)
    f = Fernet(key)
    return f.decrypt(encrypted_data).decode('utf-8')

def save_api_key_encrypted(api_key: str, filename: str = "key.enc"):
    encrypted = encrypt_data(api_key)
    with open(filename, "wb") as f:
        f.write(encrypted)
    logger.info("API密钥已加密保存到 key.enc")

def load_api_key_encrypted(filename: str = "key.enc") -> str | None:
    if not os.path.exists(filename):
        return None
    try:
        with open(filename, "rb") as f:
            encrypted = f.read()
        return decrypt_data(encrypted)
    except Exception as e:
        logger.error(f"解密密钥失败: {e}")
        return None

class FofaGUIApp:
    def __init__(self, is_web=False, session_id=None):
        self.is_web = is_web
        self.session_id = session_id
        self.api_key = load_api_key_encrypted() or ""
        self.current_query = ""
        self.current_fields = "host,ip,port"
        self.page_size = 1000
        self.results_data = []
        self.fields_list = []
        self.total_results = 0

        # 初始化下载服务器会话目录
        if self.is_web and self.session_id:
            session_dir = os.path.join("web_exports", self.session_id)
            if not os.path.exists(session_dir):
                os.makedirs(session_dir)
            download_server.add_session_dir(self.session_id, session_dir)

    @staticmethod
    def retry_decorator(max_retries=3, delay=2):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                retries = 0
                while retries < max_retries:
                    try:
                        return func(*args, **kwargs)
                    except requests.exceptions.RequestException as e:
                        retries += 1
                        if retries >= max_retries:
                            logger.error(f"达到最大重试次数 {max_retries}，请求失败: {str(e)}")
                            raise
                        logger.warning(f"请求失败，将在 {delay} 秒后重试 (第 {retries}/{max_retries} 次): {str(e)}")
                        time.sleep(delay)
            return wrapper
        return decorator

    @retry_decorator(max_retries=3, delay=3)
    def fofa_search(self, query, fields="host,ip,port", page=1, size=10):
        try:
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)
            query_bytes = query.encode('utf-8')
            qbase64 = base64.b64encode(query_bytes).decode('utf-8')
            url = "https://fofa.info/api/v1/search/all"
            params = {
                "key": self.api_key,
                "qbase64": qbase64,
                "fields": fields,
                "page": page,
                "size": size
            }
            logger.info(f"正在查询: {query}, 字段: {fields}, 页码: {page}, 每页: {size}")
            response = session.get(url, params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            if result.get("error", False):
                error_msg = result.get('errmsg', '未知错误')
                logger.error(f"API错误: {error_msg}")
                return None, error_msg
            logger.info(f"成功获取第 {page} 页数据，共 {len(result.get('results', []))} 条记录")
            return result, None
        except requests.exceptions.RequestException as e:
            logger.error(f"请求出错: {str(e)}")
            return None, str(e)
        except json.JSONDecodeError:
            logger.error("无法解析API返回的JSON数据")
            return None, "无法解析API返回的JSON数据"
        except Exception as e:
            logger.error(f"发生错误: {str(e)}")
            return None, str(e)

    def get_all_results(self, query, fields="host,ip,port", page_size=1000):
        all_results = []
        current_page = 1
        first_page, error = self.fofa_search(query, fields, current_page, page_size)
        if error:
            return None, None, error
        if not first_page:
            return None, None, "无法获取初始数据"

        total = first_page.get('size', 0)
        fields_list = first_page.get('fields', fields.split(','))
        if total > 100000:
            logger.warning(f"数据量过大: {total} 条，超过10万条限制")
            return None, None, f"数据量过大: {total} 条，超过10万条限制，请缩小查询范围"
        if total == 0:
            return [], fields_list, "没有找到匹配的结果"

        all_results.extend(first_page.get('results', []))
        total_pages = (total + page_size - 1) // page_size
        for page in range(2, total_pages + 1):
            time.sleep(1.5)
            page_data, error = self.fofa_search(query, fields, page, page_size)
            if error:
                logger.error(f"获取第 {page} 页数据失败: {error}")
                continue
            if not page_data:
                logger.warning(f"第 {page} 页数据为空，跳过该页")
                continue
            all_results.extend(page_data.get('results', []))

        logger.info(f"全量数据获取完成，共 {len(all_results)} 条记录")
        return all_results, fields_list, None

    def export_to_csv(self, data, fields, query, progress_callback=None):
        if not data:
            return None, "没有数据可导出"
        try:
            if self.is_web and self.session_id:
                output_dir = os.path.join("web_exports", self.session_id)
            else:
                output_dir = "fofa_results"

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            query_hash = hash(query)
            filename = f"fofa_search_{timestamp}_{query_hash}.csv"
            full_path = os.path.join(output_dir, filename)

            total_records = len(data)
            progress_update_interval = max(1, total_records // 100)  # 最多100次进度更新

            with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                header = fields + ['fofa_query']
                writer.writerow(header)

                for i, row in enumerate(data):
                    str_row = [str(item) if item is not None else "" for item in row]
                    writer.writerow(str_row + [query])

                    # 定期更新进度
                    if progress_callback and i % progress_update_interval == 0:
                        progress_callback(i)

            # 确保进度条显示100%
            if progress_callback:
                progress_callback(total_records)

            logger.info(f"数据已成功导出到: {full_path}")

            # 如果是Web模式，返回下载URL
            if self.is_web and self.session_id:
                download_url = f"http://localhost:8551/{self.session_id}/{filename}"
                return download_url, None

            return full_path, None
        except Exception as e:
            logger.error(f"导出CSV失败: {str(e)}")
            return None, str(e)

    def create_zip_for_batch(self, file_paths, base_name="batch_export"):
        if not self.is_web or not self.session_id:
            return None, "仅 Web 模式支持批量 ZIP"
        try:
            zip_dir = os.path.join("web_exports", self.session_id)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"{base_name}_{timestamp}.zip"
            zip_path = os.path.join(zip_dir, zip_filename)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fp in file_paths:
                    # 确保文件路径是绝对路径，处理可能的URL格式
                    if fp.startswith("http://"):
                        # 如果是URL，提取文件名
                        file_name = fp.split("/")[-1]
                        # 构建完整路径
                        full_path = os.path.join(zip_dir, file_name)
                        if os.path.exists(full_path):
                            arcname = os.path.basename(full_path)
                            zf.write(full_path, arcname)
                            logger.info(f"已添加文件到压缩包: {full_path} -> {arcname}")
                        else:
                            logger.warning(f"文件不存在: {full_path}")
                    else:
                        # 如果是普通路径
                        if os.path.exists(fp):
                            arcname = os.path.basename(fp)
                            zf.write(fp, arcname)
                            logger.info(f"已添加文件到压缩包: {fp} -> {arcname}")
                        else:
                            logger.warning(f"文件不存在: {fp}")

            # 检查压缩包是否为空
            if os.path.exists(zip_path):
                zip_size = os.path.getsize(zip_path)
                if zip_size == 0:
                    logger.error("创建的压缩包为空")
                    return None, "创建的压缩包为空，没有有效文件可添加"
                else:
                    logger.info(f"压缩包创建成功，大小: {zip_size} 字节")
            else:
                logger.error("压缩包文件未创建")
                return None, "压缩包文件创建失败"

            # 返回下载URL
            download_url = f"http://localhost:8551/{self.session_id}/{zip_filename}"
            return download_url, None
        except Exception as e:
            logger.error(f"创建 ZIP 失败: {e}")
            return None, str(e)

    def show_available_fields(self):
        fields_info = [
            ("ip", "ip地址", "无"),
            ("port", "端口", "无"),
            ("protocol", "协议名", "无"),
            ("country", "国家代码", "无"),
            ("country_name", "国家名", "无"),
            ("region", "区域", "无"),
            ("city", "城市", "无"),
            ("longitude", "地理位置 经度", "无"),
            ("latitude", "地理位置 纬度", "无"),
            ("asn", "asn编号", "无"),
            ("org", "asn组织", "无"),
            ("host", "主机名", "无"),
            ("domain", "域名", "无"),
            ("os", "操作系统", "无"),
            ("server", "网站server", "无"),
            ("icp", "icp备案号", "无"),
            ("title", "网站标题", "无"),
            ("jarm", "jarm 指纹", "无"),
            ("header", "网站header", "无"),
            ("base_protocol", "基础协议，比如tcp/udp", "无"),
            ("link", "资产的URL链接", "无"),
            ("cert.issuer.org", "证书颁发者组织", "无"),
            ("cert.issuer.cn", "证书颁发者通用名称", "无"),
            ("cert.subject.org", "证书持有者组织", "无"),
            ("cert.subject.cn", "证书持有者通用名称", "无"),
            ("tls.ja3s", "ja3s指纹信息", "无"),
            ("tls.version", "tls协议版本", "无"),
            ("cert.sn", "证书的序列号", "无"),
            ("cert.not_before", "证书生效时间", "无"),
            ("cert.not_after", "证书到期时间", "无"),
            ("cert.domain", "证书中的根域名", "无"),
            ("header_hash", "http/https相应信息计算的hash值", "个人版及以上"),
            ("banner_hash", "协议相应信息的完整hash值", "个人版及以上"),
            ("banner_fid", "协议相应信息架构的指纹值", "个人版及以上"),
            ("cname", "域名cname", "专业版本及以上"),
            ("lastupdatetime", "FOFA最后更新时间", "专业版本及以上"),
            ("product", "产品名", "专业版本及以上"),
            ("product_category", "产品分类", "专业版本及以上"),
            ("product.version", "产品版本号", "商业版本及以上"),
            ("icon_hash", "返回的icon_hash值", "商业版本及以上"),
            ("cert.is_valid", "证书是否有效", "商业版本及以上"),
            ("cname_domain", "cname的域名", "商业版本及以上"),
            ("cert.is_match", "证书颁发者和持有者是否相同", "商业版本及以上"),
            ("cert.is_equal", "证书和域名是否匹配", "商业版本及以上"),
            ("icon", "icon 图标", "企业会员"),
            ("fid", "fid", "企业会员"),
            ("structinfo", "结构化信息 (部分协议支持、比如elastic、mongodb)", "企业会员")
        ]
        return fields_info

    def batch_preview_queries(self, queries, fields="host,ip,port"):
        preview_results = []
        errors = []
        for i, query in enumerate(queries):
            query = query.strip()
            if not query:
                continue
            try:
                result, error = self.fofa_search(query, fields, page=1, size=1)
                if error:
                    errors.append(f"查询 {i+1}: {query} - 错误: {error}")
                    preview_results.append({
                        'query': query,
                        'total': 0,
                        'error': error,
                        'valid': False
                    })
                else:
                    total = result.get('size', 0)
                    preview_results.append({
                        'query': query,
                        'total': total,
                        'error': None,
                        'valid': total <= 200000 and total > 0
                    })
            except Exception as e:
                error_msg = f"查询 {i+1}: {query} - 异常: {str(e)}"
                errors.append(error_msg)
                preview_results.append({
                    'query': query,
                    'total': 0,
                    'error': str(e),
                    'valid': False
                })
        return preview_results, errors

    def batch_export_queries(self, queries, fields="host,ip,port", page_size=10000, progress_callback=None):
        export_results = []
        error_logs = []
        exported_files = []
        total_queries = len(queries)

        for i, query in enumerate(queries):
            # 更新进度
            if progress_callback:
                progress_callback(i, total_queries)
            query = query.strip()
            if not query:
                continue
            try:
                preview_result, error = self.fofa_search(query, fields, page=1, size=1)
                if error:
                    error_logs.append(f"查询 {i+1}: {query} - 预览失败: {error}")
                    export_results.append({
                        'query': query,
                        'success': False,
                        'filename': None,
                        'record_count': 0,
                        'error': error
                    })
                    continue
                total = preview_result.get('size', 0)
                if total > 200000:
                    error_logs.append(f"查询 {i+1}: {query} - 数据量过大: {total}条")
                    export_results.append({
                        'query': query,
                        'success': False,
                        'filename': None,
                        'record_count': 0,
                        'error': f"数据量过大: {total}条"
                    })
                    continue
                if total == 0:
                    error_logs.append(f"查询 {i+1}: {query} - 没有找到结果")
                    export_results.append({
                        'query': query,
                        'success': False,
                        'filename': None,
                        'record_count': 0,
                        'error': "没有找到结果"
                    })
                    continue

                all_data = []
                current_page = 1
                total_pages = (total + page_size - 1) // page_size
                logger.info(f"开始导出查询 {i+1}: {query}, 总数据量: {total}条, 分页大小: {page_size}")

                while current_page <= total_pages:
                    try:
                        page_data, error = self.fofa_search(query, fields, current_page, page_size)
                        if error:
                            error_logs.append(f"查询 {i+1}: {query} - 第{current_page}页失败: {error}")
                            break
                        if page_data:
                            results = page_data.get('results', [])
                            all_data.extend(results)
                            logger.info(f"查询 {i+1} - 第{current_page}页获取成功: {len(results)}条")
                        current_page += 1
                        time.sleep(1.5)
                    except Exception as e:
                        error_logs.append(f"查询 {i+1}: {query} - 第{current_page}页异常: {str(e)}")
                        break

                if all_data:
                    # 为单个查询导出创建进度回调
                    def single_query_progress(current):
                        # 将单个查询的进度映射到整体进度中
                        if progress_callback:
                            # 计算当前查询在整体进度中的位置
                            base_progress = i / total_queries
                            # 计算当前查询的进度比例
                            query_progress = current / len(all_data) if all_data else 0
                            # 计算整体进度
                            overall_progress = base_progress + (query_progress / total_queries)
                            progress_callback(int(overall_progress * total_queries), total_queries)

                    filename, error = self.export_to_csv(all_data, fields.split(','), query, progress_callback=single_query_progress)
                    if error:
                        error_logs.append(f"查询 {i+1}: {query} - 导出失败: {error}")
                        export_results.append({
                            'query': query,
                            'success': False,
                            'filename': None,
                            'record_count': len(all_data),
                            'error': error
                        })
                    else:
                        export_results.append({
                            'query': query,
                            'success': True,
                            'filename': filename,
                            'record_count': len(all_data),
                            'error': None
                        })
                        exported_files.append(filename)
                        logger.info(f"查询 {i+1}导出成功: {filename}, 记录数: {len(all_data)}")
            except Exception as e:
                error_msg = f"查询 {i+1}: {query} - 处理异常: {str(e)}"
                error_logs.append(error_msg)
                export_results.append({
                    'query': query,
                    'success': False,
                    'filename': None,
                    'record_count': 0,
                    'error': str(e)
                })

        # 确保进度条显示100%
        if progress_callback:
            progress_callback(total_queries, total_queries)

        return export_results, error_logs, exported_files


def main(page: ft.Page):
    # 设置页面属性
    page.title = "FOFA API 图形界面工具"
    page.window_min_width = 320  # 设置最小窗口宽度为手机宽度
    page.window_min_height = 600  # 设置最小窗口高度
    page.scroll = ft.ScrollMode.AUTO  # 启用页面滚动
    page.padding = 10  # 添加页面内边距

    # 检测是否为移动设备或小屏幕
    def is_mobile():
        # 如果是Web模式，检查屏幕宽度
        if page.web:
            return page.window_width <= 768
        # 如果是桌面应用，检查窗口宽度
        return page.window_width <= 768

    # 检测是否为 Web 模式
    is_web = page.web
    session_id = page.session_id if is_web else None
    app = FofaGUIApp(is_web=is_web, session_id=session_id)

    # API 密钥输入
    api_key_field = ft.TextField(
        label="FOFA API密钥",
        password=True,
        can_reveal_password=False,
        width=420,
        expand=True,  # 允许扩展填充可用空间
    )
    if app.api_key:
        api_key_field.value = app.api_key

    # 查询语句
    query_field = ft.TextField(
        label="查询语句",
        hint_text="例如: title=\"北京日报\"",
        multiline=True,
        min_lines=2,
        max_lines=4,
        width=420,
        expand=True,  # 允许扩展填充可用空间
    )

    # === 智能字段选择器（带搜索）===
    all_fields_info = app.show_available_fields()
    all_field_names = [info[0] for info in all_fields_info]
    default_selected = {"host", "ip", "port"}
    selected_fields = set(default_selected)
    field_checkboxes = {}

    fields_column = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, height=300)

    def on_field_change(field_name: str, is_checked: bool):
        if is_checked:
            selected_fields.add(field_name)
        else:
            selected_fields.discard(field_name)

    for name in all_field_names:
        cb = ft.Checkbox(
            label=name,
            value=name in default_selected,
            on_change=lambda e, n=name: on_field_change(n, e.control.value)
        )
        field_checkboxes[name] = cb

    search_field = ft.TextField(
        label="搜索字段",
        hint_text="输入字段名（如 ip, title）",
        width=320,
        dense=True,
        content_padding=8,
    )

    def filter_fields(e):
        query = search_field.value.lower().strip()
        fields_column.controls.clear()
        for name in all_field_names:
            if query in name.lower():
                fields_column.controls.append(field_checkboxes[name])
        page.update()

    search_field.on_change = filter_fields

    for name in all_field_names:
        fields_column.controls.append(field_checkboxes[name])

    def toggle_select_all(e):
        visible_names = []
        for name in all_field_names:
            if search_field.value.lower().strip() in name.lower():
                visible_names.append(name)
        if not visible_names:
            return
        all_selected = all(field_checkboxes[n].value for n in visible_names)
        new_value = not all_selected
        for name in visible_names:
            cb = field_checkboxes[name]
            cb.value = new_value
            if new_value:
                selected_fields.add(name)
            else:
                selected_fields.discard(name)
        page.update()

    select_all_button = ft.TextButton(
        "全选/反选",
        icon=ft.icons.CHECK_BOX_OUTLINED,
        on_click=toggle_select_all,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5))
    )

    fields_selection_container = ft.Container(
        content=ft.Column([
            ft.Row([search_field, select_all_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=10, thickness=1),
            ft.Container(
                content=fields_column,
                height=300,  # 固定高度
                padding=ft.padding.only(right=5),  # 添加右边距给滚动条留出空间
            ),
        ], expand=True),
        padding=12,
        border=ft.border.all(1, ft.colors.GREY_300),
        border_radius=8,
        bgcolor=ft.colors.GREY_50,
        width=420,
        height=400,
        expand=True,  # 允许扩展填充可用空间
    )

    # 每页数量
    page_size_field = ft.TextField(
        label="每页结果数量",
        value="1000",
        width=180,
    )

    # 状态与进度
    status_text = ft.Text("准备就绪", color=ft.colors.BLUE)
    progress_bar = ft.ProgressBar(width=600, visible=False)

    # 结果区域
    results_container = ft.Container(
        content=ft.Column([], scroll=ft.ScrollMode.AUTO, auto_scroll=True),
        padding=15,
        border=ft.border.all(1, ft.colors.GREY_300),
        border_radius=8,
        bgcolor=ft.colors.GREY_50,
        height=500,
        visible=False,
    )

    results_title_container = ft.Container(
        content=ft.Row([
            ft.Icon(ft.icons.LIST_ALT, color=ft.colors.BLUE),
            ft.Text("查询结果", size=18, weight=ft.FontWeight.BOLD),
        ]),
        margin=ft.margin.only(top=20, bottom=10),
        visible=False,
    )

    # 警告弹窗
    too_much_data_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("数据量过大警告"),
        content=ft.Text("数据量超过10万条限制，无法获取全量数据，请缩小查询范围。"),
        actions=[ft.TextButton("确定", on_click=lambda _: close_too_much_data_dialog())]
    )

    def close_too_much_data_dialog():
        too_much_data_dialog.open = False
        page.update()
        page.overlay.remove(too_much_data_dialog)

    # 字段说明弹窗
    fields_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("可用字段列表（含说明）"),
        content=ft.Column([], scroll=ft.ScrollMode.AUTO, height=300),
        actions=[ft.TextButton("关闭", on_click=lambda _: close_fields_dialog())]
    )

    def show_fields_dialog(e):
        fields_info = app.show_available_fields()
        fields_dialog.content.controls.clear()
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("字段名")),
                ft.DataColumn(ft.Text("描述")),
                ft.DataColumn(ft.Text("权限")),
            ],
            rows=[
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(field[0])),
                    ft.DataCell(ft.Text(field[1])),
                    ft.DataCell(ft.Text(field[2])),
                ]) for field in fields_info
            ]
        )
        fields_dialog.content.controls.append(table)
        page.overlay.append(fields_dialog)
        fields_dialog.open = True
        page.update()

    def close_fields_dialog():
        fields_dialog.open = False
        page.update()
        page.overlay.remove(fields_dialog)

    # 批量模式对话框
    batch_mode_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("批量查询模式"),
        content=ft.Column([], scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton("预览", on_click=lambda _: batch_preview()),
            ft.TextButton("导出", on_click=lambda _: batch_export()),
            ft.TextButton("关闭", on_click=lambda _: close_batch_mode_dialog())
        ]
    )

    batch_query_field = ft.TextField(
        label="批量查询语句",
        hint_text="每行一个查询语句，例如:\ntitle=\"北京日报\"\nport=80\nbody=\"登录\"",
        multiline=True,
        min_lines=8,
        max_lines=12,
        width=600,
    )

    batch_preview_results = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("序号")),
            ft.DataColumn(ft.Text("查询语句")),
            ft.DataColumn(ft.Text("数据量")),
            ft.DataColumn(ft.Text("状态"))
        ],
        rows=[],
        width=600,
    )

    batch_error_logs = ft.TextField(
        label="错误日志",
        multiline=True,
        min_lines=4,
        max_lines=8,
        width=600,
        visible=False,
    )

    batch_progress_bar = ft.ProgressBar(width=600, visible=False)

    def show_batch_mode_dialog():
        batch_mode_dialog.content.controls.clear()
        batch_mode_dialog.content.controls.extend([
            batch_query_field,
            ft.Container(height=10),
            ft.Text("预览结果:", weight=ft.FontWeight.BOLD),
            ft.Container(
                content=batch_preview_results,
                padding=10,
                border=ft.border.all(1, ft.colors.GREY_300),
                border_radius=5
            ),
            ft.Container(height=10),
            batch_error_logs,
            batch_progress_bar
        ])
        batch_preview_results.rows.clear()
        batch_error_logs.value = ""
        batch_error_logs.visible = False
        batch_progress_bar.visible = False
        page.overlay.append(batch_mode_dialog)
        batch_mode_dialog.open = True
        page.update()

    def close_batch_mode_dialog():
        batch_mode_dialog.open = False
        page.update()
        page.overlay.remove(batch_mode_dialog)

    def batch_preview():
        if not api_key_field.value:
            update_status("请输入API密钥", ft.colors.RED)
            return
        if not batch_query_field.value:
            update_status("请输入批量查询语句", ft.colors.RED)
            return
        if not selected_fields:
            update_status("请至少选择一个查询字段", ft.colors.RED)
            return

        api_key = api_key_field.value.strip()
        queries = [q.strip() for q in batch_query_field.value.strip().split('\n') if q.strip()]
        fields = ",".join(sorted(selected_fields))
        app.api_key = api_key

        batch_preview_results.rows.clear()
        batch_error_logs.value = ""
        batch_error_logs.visible = False
        page.update()

        update_status("正在批量预览查询...", ft.colors.ORANGE)
        preview_results, errors = app.batch_preview_queries(queries, fields)
        for i, result in enumerate(preview_results):
            status_text = "有效" if result['valid'] else "无效"
            status_color = ft.colors.GREEN if result['valid'] else ft.colors.RED
            if result['error']:
                status_text = f"错误: {result['error']}"
                status_color = ft.colors.RED
            batch_preview_results.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(i + 1))),
                        ft.DataCell(ft.Text(result['query'], selectable=True)),
                        ft.DataCell(ft.Text(str(result['total']))),
                        ft.DataCell(ft.Text(status_text, color=status_color))
                    ]
                )
            )
        if errors:
            batch_error_logs.value = "\n".join(errors)
            batch_error_logs.visible = True
        page.update()
        update_status("批量预览完成", ft.colors.GREEN)

    def batch_export():
        if not api_key_field.value:
            update_status("请输入API密钥", ft.colors.RED)
            return
        if not batch_query_field.value:
            update_status("请输入批量查询语句", ft.colors.RED)
            return
        if not selected_fields:
            update_status("请至少选择一个查询字段", ft.colors.RED)
            return

        api_key = api_key_field.value.strip()
        queries = [q.strip() for q in batch_query_field.value.strip().split('\n') if q.strip()]
        fields = ",".join(sorted(selected_fields))
        app.api_key = api_key

        batch_progress_bar.visible = True
        batch_progress_bar.value = 0
        batch_preview_results.rows.clear()
        batch_error_logs.value = ""
        batch_error_logs.visible = False
        page.update()

        update_status("正在批量导出数据...", ft.colors.ORANGE)

        # 定义进度回调函数
        def update_batch_progress(current, total):
            progress = min(current / total, 1.0)
            batch_progress_bar.value = progress
            page.update()

        export_results, error_logs, exported_files = app.batch_export_queries(
            queries, fields, page_size=10000, progress_callback=update_batch_progress
        )

        for i, result in enumerate(export_results):
            status_text = "成功" if result['success'] else "失败"
            status_color = ft.colors.GREEN if result['success'] else ft.colors.RED
            if result['error']:
                status_text = f"失败: {result['error']}"
                status_color = ft.colors.RED
            batch_preview_results.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(i + 1))),
                        ft.DataCell(ft.Text(result['query'], selectable=True)),
                        ft.DataCell(ft.Text(str(result['record_count']))),
                        ft.DataCell(ft.Text(status_text, color=status_color))
                    ]
                )
            )

        if error_logs:
            batch_error_logs.value = "\n".join(error_logs)
            batch_error_logs.visible = True

        batch_progress_bar.visible = False
        page.update()

        success_count = sum(1 for r in export_results if r['success'])
        total_count = len(export_results)

        if is_web and exported_files:
            # 打包 ZIP
            download_url, zip_error = app.create_zip_for_batch(exported_files)
            if zip_error:
                update_status(f"批量导出完成，但 ZIP 失败: {zip_error}", ft.colors.RED)
            else:
                results_container.content.controls.clear()
                results_container.content.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text("批量导出成功！", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN),
                            ft.Text(f"共 {success_count}/{total_count} 个查询成功", size=14),
                            ft.ElevatedButton(
                                "下载 ZIP 文件",
                                icon=ft.icons.DOWNLOAD,
                                url=download_url,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                            ),
                            ft.Text(f"下载链接: {download_url}", size=12, color=ft.colors.GREY, selectable=True)
                        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=20,
                        alignment=ft.alignment.center
                    )
                )
                results_container.visible = True
                results_title_container.visible = True
                update_status("批量导出完成，ZIP 已生成", ft.colors.GREEN)
        else:
            update_status(f"批量导出完成: {success_count}/{total_count} 个查询成功", ft.colors.GREEN)

    def update_status(message, color=ft.colors.BLUE):
        status_text.value = message
        status_text.color = color
        page.update()

    def show_preview_results(result, query, fields):
        if not result:
            results_container.content.controls.clear()
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Text("无法获取预览数据", color=ft.colors.RED),
                    padding=10,
                    bgcolor=ft.colors.RED_50,
                    border_radius=5,
                    margin=ft.margin.only(bottom=10)
                )
            )
            page.update()
            return

        app.total_results = result.get('size', 0)
        results_container.content.controls.clear()

        query_info_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.icons.INFO, color=ft.colors.BLUE),
                        title=ft.Text("查询信息", weight=ft.FontWeight.BOLD),
                    ),
                    ft.Divider(height=1, thickness=1),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([ft.Text("查询语句:", weight=ft.FontWeight.BOLD, width=110), ft.Text(query, expand=True)]),
                            ft.Row([ft.Text("查询字段:", weight=ft.FontWeight.BOLD, width=110), ft.Text(fields, expand=True)]),
                            ft.Row([ft.Text("总结果数:", weight=ft.FontWeight.BOLD, width=110), ft.Text(str(result.get('size', 0)), expand=True)]),
                            ft.Row([ft.Text("当前页码:", weight=ft.FontWeight.BOLD, width=110), ft.Text(str(result.get('page', 1)), expand=True)]),
                            ft.Row([ft.Text("消耗F点:", weight=ft.FontWeight.BOLD, width=110), ft.Text(str(result.get('consumed_fpoint', 0)), expand=True)]),
                        ], spacing=6),
                        padding=ft.padding.only(left=10, right=10, bottom=10)
                    )
                ]),
                padding=10
            ),
            elevation=2
        )
        results_container.content.controls.append(query_info_card)

        results_container.content.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.icons.LIST_ALT, color=ft.colors.BLUE),
                    ft.Text("结果列表 (前10条)", size=16, weight=ft.FontWeight.BOLD),
                ]),
                margin=ft.margin.only(top=20, bottom=10)
            )
        )

        fields_list = result.get('fields', fields.split(','))
        results_to_show = result.get('results', [])[:10]

        if not results_to_show:
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Text("没有找到结果", color=ft.colors.GREY),
                    padding=10,
                    bgcolor=ft.colors.GREY_100,
                    border_radius=5,
                    alignment=ft.alignment.center
                )
            )
            page.update()
            return

        data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("序号", weight=ft.FontWeight.BOLD), numeric=True),
                *[ft.DataColumn(ft.Text(field, weight=ft.FontWeight.BOLD)) for field in fields_list]
            ],
            rows=[
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(idx), weight=ft.FontWeight.BOLD)),
                        *[ft.DataCell(ft.Text(str(item[i]) if item[i] is not None else "", selectable=True)) for i in range(len(fields_list))]
                    ],
                    color=ft.colors.BLUE_GREY_50 if idx % 2 == 0 else None
                ) for idx, item in enumerate(results_to_show, 1)
            ],
            border=ft.border.all(1, ft.colors.GREY_300),
            heading_row_color=ft.colors.BLUE_GREY_100,
            data_row_max_height=100,
        )

        scrollable_table = ft.Row(controls=[data_table], scroll=ft.ScrollMode.ADAPTIVE, expand=False)
        table_container = ft.Container(
            content=scrollable_table,
            padding=10,
            bgcolor=ft.colors.WHITE,
            border_radius=5,
            border=ft.border.all(1, ft.colors.GREY_200),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=2, color=ft.colors.GREY_300, offset=ft.Offset(0, 1)),
            width=min(2000, page.width - 100) if page.width else 2000,
        )
        results_container.content.controls.append(table_container)

        total_results = result.get('size', 0)
        if total_results > 10:
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.INFO_OUTLINE, color=ft.colors.GREY, size=16),
                        ft.Text(f"... 还有 {total_results - 10} 条结果未显示，点击'获取全量数据'获取全部", size=12, color=ft.colors.GREY),
                    ]),
                    margin=ft.margin.only(top=10),
                    alignment=ft.alignment.center
                )
            )
        if total_results > 100000:
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.WARNING, color=ft.colors.ORANGE, size=16),
                        ft.Text(f"警告: 数据量超过10万条({total_results}条)，将无法获取全量数据", size=12, color=ft.colors.ORANGE),
                    ]),
                    margin=ft.margin.only(top=10),
                    padding=10,
                    bgcolor=ft.colors.ORANGE_50,
                    border_radius=5,
                    alignment=ft.alignment.center
                )
            )
        page.update()

    def show_full_results(count):
        results_container.content.controls.clear()
        success_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon(ft.icons.CHECK_CIRCLE, color=ft.colors.GREEN),
                        title=ft.Text("全量数据获取完成", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN),
                    ),
                    ft.Divider(height=1, thickness=1),
                    ft.Container(content=ft.Text(f"共获取 {count} 条记录", size=16), padding=ft.padding.only(left=10, right=10, bottom=10))
                ]),
                padding=10
            ),
            elevation=2
        )
        results_container.content.controls.append(success_card)

        if is_web:
            # Web 模式：提示导出后生成链接
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.INFO_OUTLINE, color=ft.colors.BLUE),
                        ft.Text("点击'导出CSV'按钮生成下载链接", size=14, color=ft.colors.BLUE),
                    ]),
                    margin=ft.margin.only(top=20),
                    padding=10,
                    bgcolor=ft.colors.BLUE_50,
                    border_radius=5,
                    alignment=ft.alignment.center
                )
            )
        else:
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.INFO_OUTLINE, color=ft.colors.BLUE),
                        ft.Text("点击'导出CSV'按钮将数据保存到本地", size=14, color=ft.colors.BLUE),
                    ]),
                    margin=ft.margin.only(top=20),
                    padding=10,
                    bgcolor=ft.colors.BLUE_50,
                    border_radius=5,
                    alignment=ft.alignment.center
                )
            )
        page.update()

    def show_export_result(filename):
        results_container.content.controls.clear()
        if is_web:
            # filename现在是下载URL
            download_url = filename
            success_card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.ListTile(
                            leading=ft.Icon(ft.icons.FILE_DOWNLOAD, color=ft.colors.GREEN),
                            title=ft.Text("数据导出成功", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN),
                        ),
                        ft.Divider(height=1, thickness=1),
                        ft.Container(
                            content=ft.Column([
                                ft.Text("点击下方按钮下载文件:", size=14),
                                ft.ElevatedButton(
                                    "下载 CSV",
                                    icon=ft.icons.DOWNLOAD,
                                    url=download_url,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                                ),
                                ft.Text(f"下载链接: {download_url}", size=12, color=ft.colors.GREY, selectable=True)
                            ]),
                            padding=ft.padding.only(left=10, right=10, bottom=10)
                        )
                    ]),
                    padding=10
                ),
                elevation=2
            )
        else:
            success_card = ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.ListTile(
                            leading=ft.Icon(ft.icons.FILE_DOWNLOAD, color=ft.colors.GREEN),
                            title=ft.Text("数据导出成功", weight=ft.FontWeight.BOLD, color=ft.colors.GREEN),
                        ),
                        ft.Divider(height=1, thickness=1),
                        ft.Container(
                            content=ft.Column([
                                ft.Text(f"文件已保存至:", size=14),
                                ft.Text(filename, size=14, weight=ft.FontWeight.BOLD, selectable=True),
                            ]),
                            padding=ft.padding.only(left=10, right=10, bottom=10)
                        )
                    ]),
                    padding=10
                ),
                elevation=2
            )
        results_container.content.controls.append(success_card)

        if not is_web:
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.FOLDER_OPEN, color=ft.colors.BLUE),
                        ft.Text("您可以在文件管理器中找到导出的CSV文件", size=14, color=ft.colors.BLUE),
                    ]),
                    margin=ft.margin.only(top=20),
                    padding=10,
                    bgcolor=ft.colors.BLUE_50,
                    border_radius=5,
                    alignment=ft.alignment.center
                )
            )
        page.update()

    def preview_search(e):
        if not api_key_field.value:
            update_status("请输入API密钥", ft.colors.RED)
            return
        if not query_field.value:
            update_status("请输入查询语句", ft.colors.RED)
            return
        if not selected_fields:
            update_status("请至少选择一个查询字段", ft.colors.RED)
            return

        api_key = api_key_field.value.strip()
        query = query_field.value.strip()
        fields = ",".join(sorted(selected_fields))
        app.api_key = api_key
        app.current_query = query
        app.current_fields = fields

        results_container.visible = True
        results_title_container.visible = True
        page.update()

        update_status("正在获取预览数据...", ft.colors.ORANGE)
        result, error = app.fofa_search(query, fields, page=1, size=10)
        if error:
            update_status(f"获取预览失败: {error}", ft.colors.RED)
            results_container.content.controls.clear()
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Text(f"错误: {error}", color=ft.colors.RED),
                    padding=10,
                    bgcolor=ft.colors.RED_50,
                    border_radius=5
                )
            )
            page.update()
            return

        show_preview_results(result, query, fields)
        update_status("预览数据获取成功", ft.colors.GREEN)

    def full_search(e):
        if not app.current_query:
            update_status("请先获取预览数据", ft.colors.RED)
            return
        if app.total_results > 100000:
            page.overlay.append(too_much_data_dialog)
            too_much_data_dialog.open = True
            page.update()
            return

        try:
            page_size = int(page_size_field.value or "1000")
            if not (1 <= page_size <= 10000):
                update_status("每页结果数量必须在1-10000之间", ft.colors.RED)
                return
        except ValueError:
            update_status("请输入有效的数字", ft.colors.RED)
            return

        app.page_size = page_size
        results_container.visible = True
        results_title_container.visible = True
        page.update()

        progress_bar.visible = True
        update_status("正在获取全量数据...", ft.colors.ORANGE)
        page.update()

        all_data, fields_list, error = app.get_all_results(app.current_query, app.current_fields, app.page_size)
        progress_bar.visible = False

        if error:
            update_status(f"获取全量数据失败: {error}", ft.colors.RED)
            results_container.content.controls.clear()
            results_container.content.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.icons.ERROR, color=ft.colors.RED, size=24),
                            ft.Text("获取全量数据失败", size=16, weight=ft.FontWeight.BOLD, color=ft.colors.RED),
                        ]),
                        ft.Container(
                            content=ft.Text(error, color=ft.colors.RED),
                            margin=ft.margin.only(top=10),
                            padding=10,
                            bgcolor=ft.colors.RED_50,
                            border_radius=5
                        )
                    ]),
                    padding=15,
                    bgcolor=ft.colors.WHITE,
                    border_radius=5,
                    border=ft.border.all(1, ft.colors.RED_200)
                )
            )
            page.update()
            return

        app.results_data = all_data
        app.fields_list = fields_list
        show_full_results(len(all_data))
        update_status("全量数据获取成功", ft.colors.GREEN)

    def export_results(e):
        if not app.results_data:
            update_status("没有数据可导出", ft.colors.RED)
            return

        results_container.visible = True
        results_title_container.visible = True
        progress_bar.visible = True
        progress_bar.value = 0
        page.update()

        update_status("正在导出数据...", ft.colors.ORANGE)

        # 模拟进度更新
        total_records = len(app.results_data)
        chunk_size = max(1, total_records // 100)  # 最多100次进度更新

        def update_progress(current):
            progress = min(current / total_records, 1.0)
            progress_bar.value = progress
            page.update()

        filename, error = app.export_to_csv(app.results_data, app.fields_list, app.current_query, progress_callback=update_progress)
        progress_bar.visible = False

        if error:
            update_status(f"导出失败: {error}", ft.colors.RED)
            return

        show_export_result(filename)
        update_status("导出成功", ft.colors.GREEN)

    def save_api_key_handler(e):
        key = api_key_field.value.strip()
        if not key:
            update_status("请输入API密钥后再保存", ft.colors.RED)
            return
        try:
            save_api_key_encrypted(key)
            update_status("密钥已加密保存", ft.colors.GREEN)
        except Exception as ex:
            logger.error(f"保存密钥失败: {ex}")
            update_status(f"保存失败: {str(ex)}", ft.colors.RED)

    # 按钮
    preview_button = ft.ElevatedButton(
        "预览查询",
        icon=ft.icons.SEARCH,
        on_click=preview_search,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2)
    )
    full_search_button = ft.ElevatedButton(
        "获取全量数据",
        icon=ft.icons.DOWNLOAD,
        on_click=full_search,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2)
    )
    export_button = ft.ElevatedButton(
        "导出CSV",
        icon=ft.icons.FILE_DOWNLOAD,
        on_click=export_results,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2)
    )
    save_key_button = ft.ElevatedButton(
        "保存密钥",
        icon=ft.icons.SAVE,
        on_click=save_api_key_handler,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2)
    )
    fields_button = ft.TextButton(
        "查看字段说明",
        icon=ft.icons.LIST,
        on_click=show_fields_dialog,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )
    batch_mode_button = ft.ElevatedButton(
        "批量模式",
        icon=ft.icons.PLAYLIST_ADD,
        on_click=lambda _: show_batch_mode_dialog(),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=2)
    )

    # === 优化布局：左右分栏 ===
    left_panel = ft.Container(
        content=ft.Column([
            api_key_field,
            query_field,
            ft.Row([page_size_field, save_key_button], spacing=12),
            ft.Row([preview_button, full_search_button, export_button], spacing=12, wrap=True),
            ft.Row([batch_mode_button, fields_button], spacing=12),
            status_text,
            progress_bar,
        ], spacing=16),
        padding=16,
        border=ft.border.all(1, ft.colors.GREY_200),
        border_radius=10,
        bgcolor=ft.colors.WHITE,
        width=450,
    )
    right_panel = ft.Container(
        content=fields_selection_container,
        width=450,
    )
    input_row = ft.Row(
        controls=[left_panel, right_panel],
        spacing=24,
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.START,
        wrap=False
    )

    # 主布局 - 添加滚动功能
    page.add(
        ft.Column([
            ft.Container(
                content=ft.Text("FOFA API 图形界面工具", size=26, weight=ft.FontWeight.BOLD),
                margin=ft.margin.only(bottom=12)
            ),
            ft.Divider(height=1, thickness=1),
            ft.Container(
                content=ft.Column([
                    input_row,
                    results_title_container,
                    results_container,
                ], spacing=24),
                expand=True
            ),
        ], 
        scroll=ft.ScrollMode.AUTO,  # 启用自动滚动
        expand=True,
        spacing=10
        )
    )


if __name__ == "__main__":
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        # 启动下载服务器
        try:
            download_server.start()
            logger.info("下载服务器已启动，监听端口8551")
        except Exception as e:
            logger.error(f"启动下载服务器失败: {e}")
            print(f"启动下载服务器失败: {e}")

        # 启动为 Web 应用（可通过浏览器访问）
        try:
            ft.app(
                target=main,
                view=ft.AppView.WEB_BROWSER,
                host="0.0.0.0",
                port=8550,
            )
        except Exception as e:
            print(f"启动 Web 应用失败: {e}")
            print("尝试使用备用配置...")
            ft.app(
                target=main,
                view=ft.AppView.WEB_BROWSER,
                host="127.0.0.1",
                port=8550
            )
    else:
        # 默认启动为桌面应用
        ft.app(target=main)
