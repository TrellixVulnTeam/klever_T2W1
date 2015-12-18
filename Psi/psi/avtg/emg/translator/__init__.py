import abc
import os
import re

from psi.avtg.emg.interfaces import Signature


class AbstractTranslator(metaclass=abc.ABCMeta):

    def __init__(self, logger, conf, avt, analysis, model):
        self.logger = logger
        self.conf = conf
        self.task = avt
        self.analysis = analysis
        self.model = model
        self.files = {}
        self.aspects = {}
        self.entry_file = None

        # Determine entry point name and file
        self.__determine_entry()

        self._generate_entry_point()
        self._generate_aspects()
        self._add_aspects()
        self._add_entry_points()
        return

    @abc.abstractmethod
    def _generate_entry_point(self):
        pass

    def __determine_entry(self):
        if len(self.analysis.inits) == 1:
            file = list(self.analysis.inits.keys())[0]
            self.logger.info("Choose file {} for entry point function".format(file))
            self.entry_file = file
        elif len(self.analysis.inits) < 1:
            raise RuntimeError("Cannot generate entry point without module initialization function")

        if "entry point" in self.conf:
            self.entry_point_name = self.conf["entry point"]
        else:
            self.entry_point_name = "main"
        self.logger.info("Genrate entry point function {}".format(self.entry_point_name))


    def _import_mapping(self):
        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    pass

    def _generate_aspects(self):
        for file in self.files:
            aspect_file = []
            aspect_file.append('after: file ("$this")\n')
            aspect_file.append('{\n')
            if "functions" in self.files[file]:
                for function in self.files[file]["functions"]:
                    lines = self.files[file]["functions"][function].get_definition()
                    aspect_file.append("\n")
                    aspect_file.extend(lines)
            aspect_file.append('}\n')

            # TODO: rewrite code below
            name = "single_hardcoded_aspect_file.aspect"
            with open("single_hardcoded_aspect_file.aspect", "w") as fh:
                fh.writelines(aspect_file)

            path = os.path.relpath(os.path.abspath(name), os.path.realpath(self.conf['source tree root']))
            self.logger.info("Add aspect file {}".format(path))
            self.aspects[file] = path

    def _add_aspects(self):
        for grp in self.task['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if cc_extra_full_desc_file["in file"] in self.aspects:
                    if 'plugin aspects' not in cc_extra_full_desc_file:
                        cc_extra_full_desc_file['plugin aspects'] = []
                    cc_extra_full_desc_file['plugin aspects'].append(
                        {
                            "plugin": "EMG",
                            "aspects": [self.aspects[cc_extra_full_desc_file["in file"]]]
                        }
                    )

    def _add_entry_points(self):
        self.task["entry points"] = [self.entry_point_name]


class Variable:

    def __init__(self, name, file, signature=Signature("void *%s")):
        self.name = name
        self.file = file
        self.signature = signature
        self.value = None


class Function:

    def __init__(self, name, file, signature=Signature("void %s(void)")):
        self.name = name
        self.file = file
        self.signature = signature
        self.export = None
        self.__body = None

    @property
    def body(self):
        if self.type_class == "function" and not self.pointer:
            if not self.__body:
                self.__body = FunctionBody()
            return self.__body
        else:
            raise TypeError("Signature '{}' with class '{}' is not a function or it is a function pointer".
                            format(self.expression, self.type_class))

    def get_definition(self):
        if self.type_class == "function" and not self.pointer:
            lines = []
            lines.append(self.expression + "{\n")
            lines.extend(self.body.get_lines(1))
            lines.append("}\n")
            return lines
        else:
            raise TypeError("Signature '{}' with class '{}' is not a function or it is a function pointer".
                            format(self.expression, self.type_class))


class FunctionBody:
    indent_re = re.compile("^(\t*)([^\s]*.*)")

    def __init__(self, body=[]):
        self.__body = []

        if len(body) > 0:
            self.concatenate(body)

    def _split_indent(self, string):
        split = self.indent_re.match(string)
        return {
            "indent": len(split.group(1)),
            "statement": split.group(2)
        }

    def concatenate(self, statements):
        for line in statements:
            splitted = self._split_indent(line)
            self.__body.append(splitted)

    def get_lines(self, start_indent=1):
        lines = []
        for splitted in self.__body:
            line = (start_indent + splitted["indent"]) * "\t" + splitted["statement"] + "\n"
            lines.append(line)
        return lines


class Entry:

    def __init__(self, logger, modules):
        self.logger = logger
        self.modules = modules

    def __load_order(self, modules):
        sorted_list = []

        unmarked = list(modules)
        self.marked = {}
        while len(unmarked) > 0:
            selected = unmarked.pop(0)
            if selected not in self.marked:
                self.__visit(selected, sorted_list, modules)

        return sorted_list

    def __visit(self, selected, sorted_list):
        if selected in self.marked and self.marked[selected] == 0:
            self.logger.debug('Given graph is not a DAG')

        elif selected not in self.marked:
            self.marked[selected] = 0

            if selected in self.modules:
                for module in self.modules[selected]:
                    self.__visit(module, sorted_list)

            self.marked[selected] = 1
            sorted_list.append(selected)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


