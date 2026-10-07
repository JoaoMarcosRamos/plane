import os, sys, json
from pathlib import Path
sys.path.insert(0, '/code')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plane.settings.test')
import django
django.setup()
from plane.radar.models import Object, PropertyValue, WorkspaceSchemaState, CommandExecution
obj = Object.objects.get(workspace__slug='u1-phase02-browser', title='Rascunho preservado após mudança de schema')
state = WorkspaceSchemaState.objects.get(workspace=obj.workspace)
value = PropertyValue.objects.get(object=obj, definition__key='description')
executions = list(CommandExecution.objects.filter(workspace=obj.workspace, command_name='UpdateObject', status='executed').order_by('created_at'))
result = {'object_id': str(obj.pk), 'object_version': obj.version, 'schema_revision': state.revision,
  'property_name': value.definition.name, 'property_value': value.value,
  'fact_intentions': [{'expected_schema_revision': e.envelope.get('expected_schema_revision'), 'expected_versions': e.envelope['expected_versions'], 'result_version': e.result['data']['object']['version']} for e in executions]}
assert obj.version == 3 and state.revision == 2
assert value.value == 'Narrativa ainda não enviada'
assert len(executions) == 2 and all(e.envelope['expected_schema_revision'] == 2 for e in executions)
Path('output/core-u1-phase-02-browser-proof-final.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
