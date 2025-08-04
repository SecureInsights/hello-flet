import flet as ft

class Task(ft.Column):
    def __init__(self, task_name, task_status_change, task_delete, completed=False):
        super().__init__()
        self.completed = completed
        self.task_name = task_name
        self.task_status_change = task_status_change
        self.task_delete = task_delete
        
        checkbox = ft.Checkbox(
            value=completed,
            on_change=self.status_changed,
        )
        
        # 创建文本组件，单行显示
        text = ft.Text(
            value=self.task_name,
            text_align=ft.TextAlign.LEFT,
            style=ft.TextStyle(
                decoration=ft.TextDecoration.LINE_THROUGH if completed else None,
                color=ft.Colors.GREY if completed else None,
                weight=ft.FontWeight.W_400
            ),
        )
        
        # 将Checkbox和Text组合在一起，并使文本可点击
        self.text_container = ft.Container(
            content=text,
            expand=True,  # 让文本占据剩余空间
            padding=ft.padding.only(left=8),  # 添加一些左侧间距
            on_click=self.text_clicked  # 添加点击事件处理
        )
        
        self.display_task = ft.Row(
            controls=[
                checkbox,
                self.text_container
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            expand=True,  # 让整个行占据可用空间
        )
        
        # 保存引用以便后续更新
        self.checkbox = checkbox
        self.task_text = text
        
        # 编辑文本框
        self.edit_name = ft.TextField(
            expand=1,
            multiline=False,  # 单行编辑
            on_submit=self.save_clicked  # 按Enter保存
        )

        # 任务显示视图
        self.display_view = ft.Container(
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,  # 顶部对齐，适应多行文本
                controls=[
                    # 使用Container包裹复选框，使其可以占据剩余空间并换行
                    ft.Container(
                        content=self.display_task,
                        expand=True,
                    ),
                    ft.Row(
                        spacing=0,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.CREATE_OUTLINED,
                                tooltip="编辑任务",
                                on_click=self.edit_clicked,
                                icon_size=22,
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除任务",
                                on_click=self.delete_clicked,
                                icon_size=22,
                            ),
                        ],
                    ),
                ],
            ),
            padding=14,
            bgcolor=ft.Colors.WHITE,
            border_radius=12,
            shadow=ft.BoxShadow(
                blur_radius=4,
                color=ft.Colors.BLACK12,
                offset=ft.Offset(0, 2)
            ),
        )

        # 任务编辑视图
        self.edit_view = ft.Container(
            visible=False,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,  # 顶部对齐
                controls=[
                    self.edit_name,
                    ft.IconButton(
                        icon=ft.Icons.DONE_OUTLINE_OUTLINED,
                        icon_color=ft.Colors.GREEN,
                        tooltip="更新任务",
                        on_click=self.save_clicked,
                        icon_size=22,
                    ),
                ],
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
        self.controls = [self.display_view, self.edit_view]

    def edit_clicked(self, e):
        self.edit_name.value = self.task_name
        self.display_view.visible = False
        self.edit_view.visible = True
        self.update()

    def save_clicked(self, e):
        # 更新任务名称
        old_name = self.task_name
        self.task_name = self.edit_name.value
        self.task_text.value = self.task_name  # 更新文本组件的值
        self.display_view.visible = True
        self.edit_view.visible = False
        self.task_status_change(self, old_name)  # 传递旧名称以便更新数据
        self.update()

    def status_changed(self, e):
        self.completed = self.checkbox.value
        if self.completed:
            self.task_text.style = ft.TextStyle(
                decoration=ft.TextDecoration.LINE_THROUGH,
                color=ft.Colors.GREY,
                overflow=ft.TextOverflow.ELLIPSIS,
                weight=ft.FontWeight.W_400
            )
        else:
            self.task_text.style = ft.TextStyle(
                decoration=None,
                color=None,
                overflow=ft.TextOverflow.ELLIPSIS,
                weight=ft.FontWeight.W_400
            )
        self.task_status_change(self)
        self.update()

    def delete_clicked(self, e):
        self.task_delete(self)
        
    def text_clicked(self, e):
        # 点击文本时切换复选框状态
        self.checkbox.value = not self.checkbox.value
        # 手动更新完成状态
        self.completed = self.checkbox.value
        # 更新文本样式
        if self.completed:
            self.task_text.style = ft.TextStyle(
                decoration=ft.TextDecoration.LINE_THROUGH,
                color=ft.Colors.GREY,
                overflow=ft.TextOverflow.ELLIPSIS,
                weight=ft.FontWeight.W_400
            )
        else:
            self.task_text.style = ft.TextStyle(
                decoration=None,
                color=None,
                overflow=ft.TextOverflow.ELLIPSIS,
                weight=ft.FontWeight.W_400
            )
        # 通知任务状态变更
        self.task_status_change(self)
        # 更新UI
        self.update()