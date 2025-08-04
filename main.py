import flet as ft
from todo_app import TodoApp

def main(page: ft.Page):
    page.title = "待办清单"
    page.bgcolor = ft.Colors.BLUE_GREY_50
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.scroll = ft.ScrollMode.ADAPTIVE
    page.padding = 10

    # 创建应用控件并添加到页面
    todo_app = TodoApp(page)  # 传入page参数
    page.add(ft.SafeArea(content=todo_app))
    page.update()  # 控件添加到页面后再更新

if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.FLET_APP)