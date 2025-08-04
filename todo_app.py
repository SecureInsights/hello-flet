import flet as ft
from models import load_tasks, save_tasks
from task import Task

class TodoApp(ft.Column):
    def __init__(self, page: ft.Page):  # 接收page参数
        super().__init__()
        self.page = page  # 保存page引用
        self.tasks_data = load_tasks()
        self.new_task = ft.TextField(
            hint_text="输入新任务…", 
            on_submit=self.add_clicked, 
            expand=True,
            border_radius=24,
            filled=True,
            bgcolor=ft.Colors.WHITE,
            content_padding=ft.padding.symmetric(horizontal=18, vertical=14),
            multiline=False,  # 禁用多行输入，确保Enter键添加任务
            shift_enter=False  # 禁用Shift+Enter换行
        )
        self.tasks = ft.Column(spacing=6)

        self.filter = ft.Tabs(
            scrollable=False,
            selected_index=0,
            on_change=self.tabs_changed,
            tabs=[ft.Tab(text="全部"), ft.Tab(text="进行中"), ft.Tab(text="已完成")],
        )

        self.items_left = ft.Text("0 项任务剩余")

        self.width = 600
        self.controls = [
            # 标题
            ft.Container(
                content=ft.Text("待办清单", size=24, weight=ft.FontWeight.W_600),
                padding=ft.padding.only(left=16, top=8, bottom=8)
            ),
            # 输入栏
            ft.Container(
                content=ft.Row(
                    controls=[
                        self.new_task,
                        ft.FloatingActionButton(
                            icon=ft.Icons.ADD, 
                            on_click=self.add_clicked,
                            mini=True,
                            bgcolor=ft.Colors.BLUE
                        ),
                    ],
                    spacing=8
                ),
                padding=ft.padding.symmetric(horizontal=16, vertical=6)
            ),
            # 分割线
            ft.Divider(height=1, thickness=1, color=ft.Colors.BLUE_GREY_200),
            # 任务区域
            ft.Column(
                spacing=25,
                controls=[
                    self.filter,
                    self.tasks,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.items_left,
                            ft.OutlinedButton(
                                text="清除已完成", on_click=self.clear_clicked
                            ),
                        ],
                    ),
                ],
            ),
        ]
        self.build_list(initial=True)  # 初始构建，不调用update

    def build_list(self, initial=False):
        self.tasks.controls.clear()
        if not self.tasks_data:
            self.tasks.controls.append(
                ft.Container(
                    content=ft.Text("暂无任务，快来添加吧！", size=16, color=ft.Colors.GREY),
                    alignment=ft.alignment.center,
                    padding=ft.padding.only(top=40)
                )
            )
        else:
            for item in self.tasks_data:
                task = Task(
                    item["text"], 
                    self.task_status_change, 
                    self.task_delete, 
                    item["done"]
                )
                self.tasks.controls.append(task)
        self.update_saved_tasks(initial=initial)

    def add_clicked(self, e):
        if self.new_task.value and self.new_task.value.strip():
            self.tasks_data.append({"text": self.new_task.value.strip(), "done": False})
            self.new_task.value = ""
            self.new_task.focus()
            self.build_list()
            self.page.update()  # 使用page.update()替代self.update()

    def task_status_change(self, task, old_name=None):
        # 更新数据状态
        for i, item in enumerate(self.tasks_data):
            # 如果是编辑任务，使用旧名称匹配
            if (old_name and item["text"] == old_name) or (not old_name and item["text"] == task.task_name):
                self.tasks_data[i]["text"] = task.task_name
                self.tasks_data[i]["done"] = task.completed
                break
        self.update_saved_tasks()
        self.page.update()  # 使用page.update()替代self.update()

    def task_delete(self, task):
        # 从数据中删除任务
        for i, item in enumerate(self.tasks_data):
            if item["text"] == task.task_name and item["done"] == task.completed:
                self.tasks_data.pop(i)
                break
        self.build_list()
        self.page.update()  # 使用page.update()替代self.update()

    def tabs_changed(self, e):
        self.update_filter()
        self.page.update()  # 使用page.update()替代self.update()

    def clear_clicked(self, e):
        # 清除已完成的任务
        self.tasks_data = [task for task in self.tasks_data if not task["done"]]
        self.build_list()
        self.page.update()  # 使用page.update()替代self.update()

    def update_saved_tasks(self, initial=False):
        save_tasks(self.tasks_data)
        self.update_filter(initial=initial)

    def update_filter(self, initial=False):
        status = self.filter.tabs[self.filter.selected_index].text
        count = 0
        has_visible_tasks = False
        
        for task in self.tasks.controls:
            if isinstance(task, Task):
                # 确定任务是否应该可见
                visible = (
                    status == "全部"
                    or (status == "进行中" and not task.completed)
                    or (status == "已完成" and task.completed)
                )
                task.visible = visible
                if visible:
                    has_visible_tasks = True
                if not task.completed:
                    count += 1
            else:
                # 处理"暂无任务"提示
                task.visible = not has_visible_tasks
        
        self.items_left.value = f"{count} 项任务剩余"
        
        # 初始构建时不调用update，因为控件还未添加到页面
        if not initial:
            self.page.update()