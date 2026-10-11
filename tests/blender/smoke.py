import bpy
import threading

assert threading.current_thread() is threading.main_thread()
assert bpy.context.scene is not None
assert len(bpy.data.objects) == 3, 'Expected isolated factory scene'
print('BAR_HEADLESS_OK')
