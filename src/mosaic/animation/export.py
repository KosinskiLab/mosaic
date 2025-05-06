class AnimationExecutor:
    """Executes animations based on their type and parameters"""

    def __init__(self, vtk_widget):
        self.vtk_widget = vtk_widget
        self.animations = []

    def add_animation(self, animation):
        """Add an animation to the executor"""
        self.animations.append(animation)

    def remove_animation(self, animation_id):
        """Remove an animation by ID"""
        self.animations = [a for a in self.animations if id(a) != animation_id]

    def update(self, global_frame):
        """Update all animations for the current global frame"""
        for animation in self.animations:
            animation.update(global_frame)
        self.vtk_widget.GetRenderWindow().Render()
