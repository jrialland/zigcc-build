import demo
import demo_package

def test_hello_world():
    assert demo.world() == "Hello from Zig CC with Macro and Dynamic Macro!"

def test_pure_python():
    assert demo_package.greet("World") == "Hello, World from pure python!"
