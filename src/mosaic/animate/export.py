class AnimationExecutor:
    """Executes animations based on their type and parameters"""

    def __init__(self, vtk_widget, data_context):
        self.vtk_widget = vtk_widget
        self.data_context = data_context

    def create_animation(self, animation: Animation):
        """Create the appropriate animation handler"""
        if animation.type == AnimationType.TRAJECTORY:
            return self._create_trajectory_animation(animation)
        elif animation.type == AnimationType.VOLUME:
            return self._create_volume_animation(animation)
        # ... other animation types ...

    def _create_trajectory_animation(self, animation):
        geometries = animation.parameters.get("geometries", [])

        def update(frame):
            local_frame = frame - animation.start_frame
            if 0 <= local_frame < animation.stop_frame - animation.start_frame:
                display_frame = animation.start_frame + (local_frame * animation.stride)
                for geometry in geometries:
                    geometry.display_frame(display_frame)
            self.vtk_widget.GetRenderWindow().Render()

        return update

    def _create_volume_animation(self, animation):
        viewer = animation.parameters.get("viewer")
        if not viewer:
            return lambda frame: None

        def update(frame):
            local_frame = frame - animation.start_frame
            if 0 <= local_frame < animation.stop_frame - animation.start_frame:
                slice_num = animation.start_frame + (local_frame * animation.stride)
                viewer.slice_slider.setValue(slice_num)
            self.vtk_widget.GetRenderWindow().Render()

        return update
