import qtawesome as qta

from .stylesheets import Colors

dialog_margin = (16, 16, 16, 16)
footer_margin = (0, 16, 0, 0)

dialog_accept_icon = qta.icon("ph.caret-right", color=Colors.PRIMARY)
dialog_reject_icon = qta.icon("ph.x", color=Colors.ICON)

dialog_next_icon = qta.icon("ph.skip-forward", color=Colors.PRIMARY)
dialog_previous_icon = qta.icon("ph.skip-back", color=Colors.PRIMARY)
dialog_apply_icon = qta.icon("ph.checks", color=Colors.PRIMARY)

dialog_selectall_icon = qta.icon("ph.check-square", color=Colors.PRIMARY)
dialog_selectnone_icon = qta.icon("ph.x-square", color=Colors.PRIMARY)

info_icon = qta.icon("ph.info", color=Colors.PRIMARY).pixmap(18, 18)

cluster_icon = None
model_icon = None
