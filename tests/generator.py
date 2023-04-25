#
# This file is part of the PyMeasure package.
#
# Copyright (c) 2013-2023 PyMeasure Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import io
import logging

from pymeasure.adapters import VISAAdapter

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def write_generic_test(file, name, cls_name, header_text, comm_text, test, inkwargs=None):
    """Write a generic test.

    :param file: File to write to.
    :param str name: Name of the test.
    :param cls_name: Name of the instrument class.
    :param list comm_pairs: List of communication pairs.
    :param str test: Test to assert for.
    :param dict inkwargs: Dictionary of instrument instantiation kwargs.
    """
    if inkwargs is None:
        args_text = "",
    else:
        args_text = [f'            {key}={repr(value)},\n' for key, value in inkwargs.items()]
    inst = " as inst" if "inst" in test else ""
    file.writelines([
        "\n",
        "\n",
        *header_text,
        "    with expected_protocol(\n",
        f"            {cls_name},\n",
        *comm_text,
        *args_text,
        f"    ){inst}:\n",
        f"        {test}\n"
    ])


def write_test(file, name, cls_name, comm_pairs, test, inkwargs=None):
    """Write a single test.

    :param file: File to write to.
    :param str name: Name of the test.
    :param cls_name: Name of the instrument class.
    :param list comm_pairs: List of communication pairs.
    :param str test: Test to assert for.
    :param dict inkwargs: Dictionary of instrument instantiation kwargs.
    """
    write_generic_test(file, name, cls_name, [f"def test_{name}():\n"],
                       [f"            {comm_pairs},\n".replace("), (", "),\n             (")],
                       test=test,
                       inkwargs=inkwargs,
                       )


def write_parametrized_test(file, name, cls_name, comm_pairs_list, values_list, test,
                            inkwargs=None):
    """Write a parametrized test.

    :param file: File to write to.
    :param str name: Name of the test.
    :param cls_name: Name of the instrument class.
    :param list comm_pairs_list: List of communication pairs list for each test
    :param list values_list: List of expected values.
    :param str test: Test to assert for. :code:`'value'` is the expected parametrized value.
    :param dict inkwargs: Dictionary of instrument instantiation kwargs.
    """
    params = [f"    ({cp},\n     {v}),\n".replace(
        "), (", "),\n      (") for cp, v in zip(comm_pairs_list, values_list)]
    write_generic_test(file, name, cls_name,
                       header_text=['@pytest.mark.parametrize("comm_pairs, value", (\n',
                                    *params,
                                    "))\n",
                                    f"def test_{name}(comm_pairs, value):\n",
                                    ],
                       comm_text=["            comm_pairs,\n"],
                       test=test,
                       inkwargs=inkwargs,
                       )


def write_parametrized_method_test(file, name, cls_name, comm_pairs_list, args_list, kwargs_list,
                                   values_list, test, inkwargs=None):
    """Write a parametrized test for a method.

    :param file: File to write to.
    :param str name: Name of the test.
    :param cls_name: Name of the instrument class.
    :param list comm_pairs_list: List of communication pairs list for each test
    :param list args_list: List of arguments lists for the method.
    :param list kwargs_list: List of keyword dictionaries for the method.
    :param list values_list: List of expected values.
    :param str test: Test to assert for. :code:`'value'` is the expected parametrized value.
    :param dict inkwargs: Dictionary of instrument instantiation kwargs.
    """
    z = zip(comm_pairs_list, args_list, kwargs_list, values_list)
    params = [f"    ({cp},\n     {a}, {k}, {v}),\n".replace(
        "), (", "),\n      (") for cp, a, k, v in z]
    write_generic_test(file, name, cls_name,
                       ['@pytest.mark.parametrize("comm_pairs, args, kwargs, value", (\n',
                        *params,
                        "))\n",
                        f"def test_{name}(comm_pairs, args, kwargs, value):\n",
                        ],
                       comm_text=["            comm_pairs,\n"],
                       test=test,
                       inkwargs=inkwargs
                       )


def parse_stream(stream):
    """
    Parse the data stream.

    It is expected, that a message is always written in one write, while
    reading may extend over several reads, e.g. reading bytes.
    """
    comm = []
    lines = stream.readlines()
    write = None
    read = None
    mode = None
    for line in lines:
        if line.startswith(b"WRITE:"):
            # Store the last comm_pair unless there is none.
            if write is not None or read is not None:
                comm.append((write, read))
                read = None
            write = line[6:-1]
            mode = "W"
        elif line.startswith(b"READ:"):
            if read is not None:
                read += line[5:-1]
            else:
                read = line[5:-1]
            mode = "R"
        else:
            # newline due to "\n" character in communication
            if mode == "W":
                write += b"\n" + line[:-1]
            elif mode == "R":
                read += b"\n" + line[:-1]
            else:
                raise ValueError("Very first line does not contain 'WRITE' or 'READ'!")
    if read is not None or write is not None:
        comm.append((write, read))
    return comm


class ByteFormatter(logging.Formatter):
    """Logging formatter with bytes values for the test generation."""

    @staticmethod
    def make_bytes(value):
        if isinstance(value, (bytes, bytearray)):
            return value
        if isinstance(value, str):
            return value.encode()

    def format(self, record):
        return b"".join((record.msg.replace(r"%s", "").encode(),
                         *[self.make_bytes(arg) for arg in record.args]))


class ByteStreamHandler(logging.StreamHandler):
    """Logging handler using bytes streams."""

    terminator = b"\n"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatter = ByteFormatter()


class Generator:
    """
    Generates tests from the communication with an instrument.

    Example usage:
    .. code::

        g = Generator()
        g.instantiate(TC038, "COM5", 'hcp')
        g.test_property("information")
        g.test_property("monitored_value")
        g.test_property_setter("setpoint", 20)
        g.test_property("setpoint")
        g.write_file("test_tc038.py")
    """

    def __init__(self):
        self._stream = io.BytesIO()
        self._index = 0
        self._incomm = []  # Initializiation comm_pairs
        # Dictionaries for parametrized tests
        self._getters = {}
        self._setters = {}
        self._calls = {}

    def write_init_test(self, file):
        """Write the header and init test."""
        file.write(self._header)
        write_test(file, "init", self._class, self._incomm,
                   "pass  # Verify the expected communication.",
                   self._inkwargs,
                   )

    def write_getter_tests(self, file):
        """Write all parametrized getters tests."""
        for property, value in self._getters.items():
            if len(value[0]) == 1:
                v = value[1][0]
                comparison = "is" if isinstance(v, bool) or v is None else "=="
                write_test(file, property + "_getter", self._class, value[0][0],
                           f"assert inst.{property} {comparison} {v}",
                           self._inkwargs,
                           )
            else:
                write_parametrized_test(file, property + "_getter", self._class,
                                        value[0], value[1],
                                        f"assert inst.{property} == value",
                                        self._inkwargs,
                                        )

    def write_setter_tests(self, file):
        """Write all parametrized setters tests."""
        for property, value in self._setters.items():
            if len(value[0]) == 1:
                v = value[1][0]
                write_test(file, property + "_setter", self._class, value[0][0],
                           f"inst.{property} = {v}")
            else:
                write_parametrized_test(file, property + "_setter", self._class,
                                        *value,
                                        f"inst.{property} = value",
                                        self._inkwargs,
                                        )

    def write_method_tests(self, file):
        """Write all parametrized method tests."""
        for method, value in self._calls.items():
            if len(value[0]) == 1:
                v = value[-1][0]
                comparison = "is" if isinstance(v, bool) or v is None else "=="
                arg_string = f"*{value[1][0]}, " if value[1][0] else ""
                kwarg_string = f"**{value[2][0]}" if value[2][0] else ""
                write_test(file, method, self._class, value[0][0],
                           f"assert inst.{method}({arg_string}{kwarg_string}) {comparison} {v}",
                           self._inkwargs,
                           )
            else:
                write_parametrized_method_test(file, method, self._class,
                                               *value,
                                               f"assert inst.{method}(*args, **kwargs) == value",
                                               self._inkwargs,
                                               )

    def write_file(self, filename="tests.py"):
        """Write the tests into the file.

        :param filename: Name to save the tests to, may contain the path, e.g. "/tests/test_abc.py".
        """
        if isinstance(filename, io.StringIO):
            file = filename
        else:
            file = open(filename, "w")
        self.write_init_test(file)
        self.write_getter_tests(file)
        self.write_setter_tests(file)
        self.write_method_tests(file)
        file.close()

    def parse_stream(self):
        """Parse the stream not yet read."""
        self._stream.seek(self._index)
        comm = parse_stream(self._stream)
        self._index = self._stream.tell()
        return self._incomm + comm

    def instantiate(self, instrument_class, adapter, manufacturer, adapter_kwargs=None, **kwargs):
        """
        Instantiate the instrument and store the istantiation communication.

        ..note::

            You have to give all keyword arguments necessary for adapter instantiation in
            `adapter_kwargs`, even those, which are defined in the instrument's
            `__init__` method.

        :param instrument_class: Class of the instrument to test.
        :param adapter: Adapter (instance or str) for the instrument instantiation.
        :param manufacturer: Module from which to import the instrument, e.g. 'hcp' if
            instrument_class is 'pymeasure.hcp.tc038'.
        :param adapter_kwargs: Keyword arguments for the adapter instantiation (see note above).
        :param \\**kwargs: Keyword arguments for the instrument instantiation.
        """
        self._class = instrument_class.__name__
        log.info(f"Instantiate {self._class}.")
        self._header = (
            "import pytest\n\n"
            "from pymeasure.test import expected_protocol\n"
            f"from pymeasure.instruments.{manufacturer} import {self._class}\n")
        if isinstance(adapter, (int, str)):
            if adapter_kwargs is None:
                adapter_kwargs = {}
            try:
                adapter = VISAAdapter(adapter, **adapter_kwargs)
            except ImportError:
                raise Exception("Invalid Adapter provided for Instrument since"
                                " PyVISA is not present")
        adapter.log.addHandler(ByteStreamHandler(self._stream))
        adapter.log.setLevel(logging.DEBUG)
        self.inst = instrument_class(adapter, **kwargs)
        self._incomm = self.parse_stream()  # communication of instantiation.
        self._inkwargs = kwargs  # instantiation kwargs

    def test_property_getter(self, property):
        """Test getting the `property` of the instrument, adding it to the list."""
        log.info(f"Test property {property} getter.")
        value = getattr(self.inst, property)
        comm = self.parse_stream()
        if property not in self._getters:
            self._getters[property] = [], []
        c, v = self._getters[property]
        c.append(comm)
        v.append(f"\'{value}\'" if isinstance(value, str) else value)
        return value

    def test_property_setter(self, property, value):
        """Test setting the `property` of the instrument to `value`, adding it to the list."""
        log.info(f"Test property {property} setter.")
        setattr(self.inst, property, value)
        comm = self.parse_stream()
        if property not in self._setters:
            self._setters[property] = [], []
        c, v = self._setters[property]
        c.append(comm)
        v.append(f"\'{value}\'" if isinstance(value, str) else value)

    def test_method(self, method, *args, **kwargs):
        """Test calling the `method` of the instruments with `args` and `kwargs`."""
        log.info(f"Test method {method}.")
        value = getattr(self.inst, method)(*args, **kwargs)
        comm = self.parse_stream()
        if method not in self._calls:
            self._calls[method] = [], [], [], []
        c, a, k, v = self._calls[method]
        c.append(comm)
        a.append(args)
        k.append(kwargs)
        v.append(f"\'{value}\'" if isinstance(value, str) else value)

    # batch tests
    def test_property_setter_batch(self, property, values):
        """Test setting `property` to each element in `values`."""
        for value in values:
            self.test_property_setter(property, value)
