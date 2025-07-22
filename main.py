import os
import pickle
from pathlib import Path
import flet as ft

SAVE_FILE = Path.home() / "todo_save.pkl"

# ---------- 持久化 ----------
def load_tasks():
    return pickle.load(open(SAVE_FILE, "rb")) if SAVE_FILE.exists() else []

def save_tasks(tasks):
    pickle.dump(tasks, open(SAVE_FILE, "wb"))

# ---------- 主界面 ----------
def main(page: ft.Page):
    page.title = "待办清单"
    page.bgcolor = ft.Colors.BLUE_GREY_50
    page.scroll = ft.ScrollMode.ADAPTIVE     # 整页滚动，防止键盘遮挡

    # 读取数据
    tasks = load_tasks()

    # 统一内边距
    PAD = 16

    todo_list = ft.Column(spacing=6)

    def add_task(e):
        text = new_task_field.value.strip()
        if not text:
            return
        tasks.append({"text": text, "done": False})
        new_task_field.value = ""
        build_list()
        save_tasks(tasks)

    def toggle_done(checkbox, index):
        tasks[index]["done"] = checkbox.value
        build_list()
        save_tasks(tasks)

    def delete_task(index):
        tasks.pop(index)
        build_list()
        save_tasks(tasks)

    def build_list():
        todo_list.controls.clear()
        if not tasks:
            todo_list.controls.append(
                ft.Container(
                    content=ft.Text("暂无任务，快来添加吧！", color=ft.Colors.GREY, size=16),
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
                todo_list.controls.append(
                    ft.Container(
                        content=ft.Row([checkbox, label, delete_btn],
                                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        padding=ft.padding.all(14),
                        bgcolor=ft.Colors.WHITE,
                        border_radius=12,
                        shadow=ft.BoxShadow(blur_radius=4,
                                            color=ft.Colors.BLACK12,
                                            offset=ft.Offset(0, 2))
                    )
                )
        page.update()

    new_task_field = ft.TextField(
        hint_text="输入新任务…",
        expand=True,
        border_radius=24,
        filled=True,
        bgcolor=ft.Colors.WHITE,
        content_padding=ft.padding.symmetric(horizontal=18, vertical=14),
        on_submit=add_task
    )

    build_list()

    page.add(
        ft.SafeArea(                       # 自动避开刘海/导航条
            content=ft.Column(
                [
                    # 标题
                    ft.Container(
                        content=ft.Text("待办清单", size=24, weight=ft.FontWeight.W_600),
                        padding=ft.padding.only(left=PAD, top=8, bottom=8)
                    ),
                    # 输入栏
                    ft.Container(
                        content=ft.Row([
                            new_task_field,
                            ft.FloatingActionButton(
                                icon=ft.Icons.ADD,
                                on_click=add_task,
                                mini=True,
                                bgcolor=ft.Colors.BLUE
                            )
                        ], spacing=8),
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

# ---------- 入口 ----------
if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.FLET_APP, assets_dir="assets")
