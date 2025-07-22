# todo.py
import json
import os
from pathlib import Path

import flet as ft

# ------------------------------------------------------------------
# 数据持久化：Android 私有目录 /data/data/<package>/files/todo.json
# ------------------------------------------------------------------
SAVE_PATH = Path(os.environ.get("HOME", ".")) / "todo.json"

def load_tasks() -> list[dict]:
    if SAVE_PATH.exists():
        try:
            return json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_tasks(tasks: list[dict]) -> None:
    SAVE_PATH.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------
# 主界面
# ------------------------------------------------------------------
def main(page: ft.Page):
    page.title = "待办清单"
    page.bgcolor = ft.Colors.BLUE_GREY_50
    page.scroll = ft.ScrollMode.ADAPTIVE  # 键盘弹出时自动滚动

    # 读取本地数据
    tasks = load_tasks()

    PAD = 16  # 统一内边距
    todo_list = ft.Column(spacing=6)

    # ---------------- 构建列表 ----------------
    def build_list():
        todo_list.controls.clear()
        if not tasks:
            todo_list.controls.append(
                ft.Container(
                    content=ft.Text("暂无任务，快来添加吧！", size=16, color=ft.Colors.GREY),
                    alignment=ft.alignment.center,
                    padding=ft.padding.only(top=40)
                )
            )
        else:
            for idx, item in enumerate(tasks):
                checkbox = ft.Checkbox(
                    value=item["done"],
                    on_change=lambda e, i=idx: toggle_done(e.control, i)
                )
                label = ft.Text(
                    item["text"],
                    size=17,
                    expand=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    style=ft.TextStyle(
                        decoration=ft.TextDecoration.LINE_THROUGH if item["done"] else None,
                        color=ft.Colors.GREY if item["done"] else None
                    )
                )
                delete_btn = ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_size=22,
                    tooltip="删除",
                    on_click=lambda _, i=idx: delete_task(i)
                )
                card = ft.Container(
                    content=ft.Row(
                        [checkbox, label, delete_btn],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    padding=14,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=12,
                    shadow=ft.BoxShadow(
                        blur_radius=4,
                        color=ft.Colors.BLACK12,
                        offset=ft.Offset(0, 2)
                    )
                )
                todo_list.controls.append(card)
        page.update()

    # ---------------- 事件处理 ----------------
    def add_task(e):
        text = new_task_field.value.strip()
        if not text:
            return
        tasks.append({"text": text, "done": False})
        new_task_field.value = ""
        save_tasks(tasks)
        build_list()

    def toggle_done(checkbox, index):
        tasks[index]["done"] = checkbox.value
        save_tasks(tasks)
        build_list()

    def delete_task(index):
        tasks.pop(index)
        save_tasks(tasks)
        build_list()

    # ---------------- 输入栏 ----------------
    new_task_field = ft.TextField(
        hint_text="输入新任务…",
        expand=True,
        border_radius=24,
        filled=True,
        bgcolor=ft.Colors.WHITE,
        content_padding=ft.padding.symmetric(horizontal=18, vertical=14),
        on_submit=add_task
    )

    # ---------------- 初始渲染 ----------------
    build_list()

    page.add(
        ft.SafeArea(
            content=ft.Column(
                [
                    # 标题
                    ft.Container(
                        content=ft.Text("待办清单", size=24, weight=ft.FontWeight.W_600),
                        padding=ft.padding.only(left=PAD, top=8, bottom=8)
                    ),
                    # 输入栏
                    ft.Container(
                        content=ft.Row(
                            [
                                new_task_field,
                                ft.FloatingActionButton(
                                    icon=ft.Icons.ADD,
                                    on_click=add_task,
                                    mini=True,
                                    bgcolor=ft.Colors.BLUE
                                )
                            ],
                            spacing=8
                        ),
                        padding=ft.padding.symmetric(horizontal=PAD, vertical=6)
                    ),
                    # 分割线
                    ft.Divider(height=1, thickness=1, color=ft.Colors.BLUE_GREY_200),
                    # 任务列表
                    ft.Container(
                        content=todo_list,
                        padding=ft.padding.symmetric(horizontal=PAD, vertical=8),
                        expand=True
                    )
                ],
                spacing=0
            )
        )
    )


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------
if __name__ == "__main__":
    # 桌面调试：python todo.py
    # 打包 APK：flet build apk todo.py
    ft.app(target=main, view=ft.AppView.FLET_APP, assets_dir="assets")
