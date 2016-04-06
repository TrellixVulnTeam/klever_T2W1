#!/usr/bin/python3

import json
import os
import string

import core.components
import core.utils


class RSG(core.components.Component):
    def generate_rule_specification(self):
        self.abstract_task_desc = self.mqs['abstract task description'].get()

        aspects = []
        models = []

        if 'files' in self.abstract_task_desc:
            self.logger.info('Get additional aspects and models specified in abstract task description')

            for file in self.abstract_task_desc['files']:
                ext = os.path.splitext(file)[1]
                if ext == '.c':
                    models.append(file)
                    self.logger.debug('Get additional model "{0}'.format(file))
                elif ext == '.aspect':
                    aspects.append(file)
                    self.logger.debug('Get additional aspect "{0}'.format(file))
                else:
                    raise ValueError('Files with extension "{0}" are not supported'.format(ext))

        self.add_aspects(aspects)
        self.add_models(models)

        if 'files' in self.abstract_task_desc:
            self.abstract_task_desc.pop('files')

        self.mqs['abstract task description'].put(self.abstract_task_desc)

    main = generate_rule_specification

    def add_aspects(self, aspects):
        self.logger.info('Add aspects to abstract task description')

        # Get common and rule specific aspects.
        for aspect in (self.conf.get('common aspects') or []) + (self.conf.get('aspects') or []):
            aspect = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], aspect)
            self.logger.debug('Get aspect "{0}"'.format(aspect))
            aspects.append(os.path.relpath(aspect, os.path.realpath(self.conf['source tree root'])))

        if not aspects:
            self.logger.warning('No aspects ase specified')
            return

        for grp in self.abstract_task_desc['grps']:
            self.logger.info('Add aspects to C files of group "{0}"'.format(grp['id']))
            for cc_extra_full_desc_file in grp['cc extra full desc files']:
                if 'plugin aspects' not in cc_extra_full_desc_file:
                    cc_extra_full_desc_file['plugin aspects'] = []
                cc_extra_full_desc_file['plugin aspects'].append({"plugin": self.name, "aspects": aspects}
                                                                 )

    def add_models(self, models):
        self.logger.info('Add models to abstract task description')

        # Get common and rule specific models.
        for model in (self.conf.get('common models') or []) + (self.conf.get('models') or []):
            model = core.utils.find_file_or_dir(self.logger, self.conf['main working directory'], model)
            self.logger.debug('Get model "{0}"'.format(model))
            models.append(os.path.relpath(model, os.path.realpath(self.conf['source tree root'])))

        if not models:
            self.logger.warning('No models are specified')
            return

        # CC extra full description files will be put to this directory as well as corresponding output files.
        os.makedirs('models')

        # Generate CC extra full description file per each model and add it to abstract task description.
        model_grp = {'id': 'models', 'cc extra full desc files': []}
        for model in models:
            out_file = os.path.join('models', '{}.c'.format(os.path.splitext(os.path.basename(model))[0]))
            full_desc_file = '{0}.json'.format(out_file)
            if os.path.isfile(full_desc_file):
                raise FileExistsError('CC extra full description file "{0}" already exists'.format(full_desc_file))
            self.logger.debug('Dump CC extra full description to file "{0}"'.format(full_desc_file))
            with open(full_desc_file, 'w', encoding='ascii') as fp:
                json.dump({
                    # Input file path should be relative to source tree root since compilation options are relative
                    # to this directory and we will change directory to that one before invoking preprocessor.
                    "in files": [model],
                    # Otput file should be located somewhere inside RSG working directory to avoid races.
                    "out file": os.path.relpath(out_file, os.path.realpath(self.conf['source tree root'])),
                    "opts":
                        [string.Template(opt).substitute(hdr_arch=self.conf['sys']['hdr arch']) for opt in
                         self.conf['model CC options']]
                }, fp, sort_keys=True, indent=4)

            model_grp['cc extra full desc files'].append({
                'cc full desc file': os.path.relpath(full_desc_file,
                                                     os.path.realpath(self.conf['source tree root'])),
                'rule spec id': self.conf['rule spec id'],
                'bug kinds': self.conf['bug kinds']
            })
        self.abstract_task_desc['grps'].append(model_grp)
        for dep in self.abstract_task_desc['deps'].values():
            dep.append(model_grp['id'])

