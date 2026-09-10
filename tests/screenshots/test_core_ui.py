import pytest

from mosaic.geometry import Geometry

from .conftest import save_widget_screenshot, make_sphere_points, make_two_blobs


@pytest.mark.gui
class TestCoreUI:

    def test_empty_interface(self, mosaic_app, output_dir, qapp):
        mosaic_app.cdata.reset()
        mosaic_app.prime_viewport_placeholder()
        qapp.processEvents()
        save_widget_screenshot(mosaic_app, output_dir / "mosaic_interface.png")

    def test_populate_data(self, mosaic_app, output_dir, qapp):
        mosaic_app.cdata.reset()

        colors = [
            (0.90, 0.35, 0.25),
            (0.25, 0.60, 0.90),
            (0.30, 0.80, 0.45),
            (0.85, 0.55, 0.20),
            (0.65, 0.30, 0.80),
        ]
        names = [
            "Segmentation",
            "Cleaned",
            "Cleaned_Outer",
            "ha_picks",
            "na_picks",
        ]

        for i, (name, color) in enumerate(zip(names, colors)):
            if i == 0:
                pts = make_sphere_points(radius=50, seed=i)
            elif i < 3:
                pts = make_sphere_points(radius=40 + i * 5, seed=i)
            else:
                pts = make_two_blobs(n_per_blob=100, separation=80 + i * 10, seed=i)

            geom = Geometry(points=pts)
            geom._meta["name"] = name
            geom.set_appearance(
                base_color=color,
                highlight_color=mosaic_app.cdata.data.container.highlight_color,
            )
            mosaic_app.cdata.data.container.add(geom)
            mosaic_app.cdata._session._order.append(geom)

        mesh_pts = make_sphere_points(radius=55, n_theta=20, n_phi=20, seed=99)
        mesh_geom = Geometry(points=mesh_pts)
        mesh_geom._meta["name"] = "InitialMesh"
        mesh_geom.set_appearance(
            base_color=(0.2, 0.4, 0.8),
            highlight_color=mosaic_app.cdata.models.container.highlight_color,
        )
        mosaic_app.cdata.models.container.add(mesh_geom)

        mosaic_app.cdata.data.render(defer_render=True)
        mosaic_app.cdata.models.render(defer_render=False)
        mosaic_app.viewport_stack.setCurrentWidget(mosaic_app.vtk_widget)
        mosaic_app.set_camera_view("z")
        qapp.processEvents()

    def test_object_browser(self, mosaic_app, output_dir, qapp):
        qapp.processEvents()
        save_widget_screenshot(
            mosaic_app.list_wrapper, output_dir / "mosaic_object_browser.png"
        )

    def test_context_menu(self, mosaic_app, output_dir, qapp):
        from qtpy.QtWidgets import QMenu

        data_list = mosaic_app.cdata.data.data_list
        tree = data_list.tree_widget

        if tree.topLevelItemCount() == 0:
            pytest.skip("No data loaded — run test_populate_data first")

        item = tree.topLevelItem(0)
        rect = tree.visualItemRect(item)
        pos = rect.center()

        original_exec = QMenu.exec

        def patched_exec(menu_self, *args, **kwargs):
            qapp.processEvents()
            save_widget_screenshot(menu_self, output_dir / "mosaic_context.png")
            menu_self.close()

        QMenu.exec = patched_exec
        try:
            tree.customContextMenuRequested.emit(pos)
            qapp.processEvents()
        finally:
            QMenu.exec = original_exec
