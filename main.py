import flet as ft

def main(page: ft.Page):
    page.title = "待办清单"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_width = 420
    page.window_height = 600
    page.bgcolor = ft.Colors.BLUE_GREY_50

    todo_list = ft.Column(scroll=ft.ScrollMode.AUTO)

    def add_task(e):
        if not task_field.value.strip():
            return
        task_text = ft.Text(
            task_field.value,
            size=16,
            expand=True,
            overflow=ft.TextOverflow.ELLIPSIS
        )
        checkbox = ft.Checkbox(on_change=task_done)

        def delete_task(e):
            todo_list.controls.remove(card)
            page.update()

        row = ft.Row([
            checkbox,
            task_text,
            ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=delete_task)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        card = ft.Container(
            content=row,
            margin=ft.margin.symmetric(vertical=4),
            padding=ft.padding.all(12),
            bgcolor=ft.Colors.WHITE,
            border_radius=10,
            shadow=ft.BoxShadow(
                blur_radius=4,
                color=ft.Colors.BLACK12,
                offset=ft.Offset(0, 2)
            )
        )
        todo_list.controls.append(card)
        task_field.value = ""
        empty_prompt.visible = False
        page.update()

    def task_done(e):
        checkbox = e.control
        row = checkbox.parent
        text = row.controls[1]
        if checkbox.value:
            text.style = ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH, color=ft.Colors.GREY)
        else:
            text.style = ft.TextStyle(decoration=None, color=None)
        page.update()

    task_field = ft.TextField(
        hint_text="输入新任务…",
        expand=True,
        border_radius=ft.border_radius.all(30),
        filled=True,
        bgcolor=ft.Colors.WHITE,
        on_submit=add_task
    )

    empty_prompt = ft.Text("暂无任务，快来添加吧！", color=ft.Colors.GREY)

    page.add(
        ft.Container(
            content=ft.Row([
                task_field,
                ft.FloatingActionButton(
                    icon=ft.Icons.ADD,
                    on_click=add_task,
                    mini=True
                )
            ]),
            padding=ft.padding.all(12)
        ),
        ft.Divider(height=1),
        ft.Container(
            content=ft.Stack([
                todo_list,
                ft.Column([empty_prompt], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
            ]),
            padding=ft.padding.symmetric(horizontal=12),
            expand=True
        )
    )

ft.app(target=main)
