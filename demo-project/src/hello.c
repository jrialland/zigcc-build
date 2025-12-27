#include <Python.h>

static PyObject* hello_world(PyObject* self, PyObject* args) {
#if defined(HELLO_MACRO) && defined(DYNAMIC_MACRO)
    return PyUnicode_FromString("Hello from Zig CC with Macro and Dynamic Macro!");
#elif defined(HELLO_MACRO)
    return PyUnicode_FromString("Hello from Zig CC with Macro!");
#else
    return PyUnicode_FromString("Hello from Zig CC!");
#endif
}

static PyMethodDef HelloMethods[] = {
    {"world", hello_world, METH_VARARGS, "Return a greeting."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef hellomodule = {
    PyModuleDef_HEAD_INIT,
    "demo",
    NULL,
    -1,
    HelloMethods
};

PyMODINIT_FUNC PyInit_demo(void) {
    return PyModule_Create(&hellomodule);
}
