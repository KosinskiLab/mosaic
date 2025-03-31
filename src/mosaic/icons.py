import qtawesome as qta

icon_color = "#4f46e5"
dialog_margin = (16, 16, 16, 16)
footer_margin = (0, 16, 0, 0)

dialog_accept_icon = qta.icon("mdi.chevron-right", color=icon_color)
dialog_reject_icon = qta.icon("mdi.close", color=icon_color)

dialog_next_icon = qta.icon("mdi6.skip-next", color=icon_color)
dialog_previous_icon = qta.icon("mdi6.skip-previous", color=icon_color)
dialog_apply_icon = qta.icon("mdi6.check-all", color=icon_color)

dialog_selectall_icon = qta.icon("mdi.select-all", color=icon_color)
dialog_selectnone_icon = qta.icon("mdi6.select-remove", color=icon_color)

info_icon = qta.icon("mdi.information-outline", color=icon_color).pixmap(18, 18)

cluster_icon = qta.icon("mdi.chart-bubble", color=icon_color)
model_icon = qta.icon("mdi.shape", color=icon_color)
cluster_icon = None
model_icon = None
