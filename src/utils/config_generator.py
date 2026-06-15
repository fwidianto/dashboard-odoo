"""Auto-generate YAML config from Odoo fields_get() API.

This utility fetches field definitions from Odoo and generates
the correct PostgreSQL type mappings automatically.

Usage:
    python -m src.utils.config_generator --model purchase.order
    python -m src.utils.config_generator --model res.partner --output config/purchase.yaml
"""

import argparse
import sys
from typing import Optional

from src.clients.odoo_client import OdooClient
from src.utils.settings import get_settings


# Odoo field type to PostgreSQL type mapping
ODOO_TYPE_TO_POSTGRES = {
    'integer': 'INTEGER',
    'bigint': 'BIGINT',
    'float': 'NUMERIC(20,4)',
    'monetary': 'NUMERIC(20,4)',
    'boolean': 'BOOLEAN',
    'char': 'TEXT',
    'text': 'TEXT',
    'selection': 'VARCHAR(255)',
    'date': 'DATE',
    'datetime': 'TIMESTAMP',
    'many2one': 'INTEGER',
    'one2many': 'SKIP',  # Not synced directly
    'many2many': 'SKIP',  # Not synced directly
    'binary': 'BYTEA',
    'html': 'TEXT',
    'reference': 'VARCHAR(255)',
}


def get_odoo_field_type(field_def: dict) -> str:
    """Get Odoo field type from field definition."""
    # Direct type
    if 'type' in field_def:
        return field_def['type']
    
    # Widget-based type inference
    widget = field_def.get('widget', '')
    if widget == 'many2one':
        return 'many2one'
    if widget == 'many2many':
        return 'many2many'
    if widget == 'one2many':
        return 'one2many'
    if widget == 'monetary':
        return 'monetary'
    
    return 'char'  # Default


def get_postgres_type(odoo_type: str) -> str:
    """Map Odoo type to PostgreSQL type."""
    return ODOO_TYPE_TO_POSTGRES.get(odoo_type, 'TEXT')


def should_skip_field(field_name: str, odoo_type: str) -> bool:
    """Determine if field should be skipped."""
    # Skip one2many and many2many (handled separately)
    if odoo_type in ('one2many', 'many2many'):
        return True
    
    # Skip binary fields by default (too large)
    if odoo_type == 'binary':
        return True
    
    # Skip internal fields
    internal_fields = {'__last_update', 'write_uid', 'create_uid'}
    if field_name in internal_fields:
        return True
    
    return False


def generate_field_config(field_name: str, field_def: dict) -> Optional[dict]:
    """Generate field configuration from Odoo field definition."""
    odoo_type = get_odoo_field_type(field_def)
    
    if should_skip_field(field_name, odoo_type):
        return None
    
    pg_type = get_postgres_type(odoo_type)
    
    config = {
        'odoo_field': field_name,
        'postgres_column': field_name,
        'postgres_type': pg_type,
    }
    
    # Primary key
    if field_name == 'id':
        config['primary_key'] = True
        config['nullable'] = False
        config['indexed'] = True
    
    # Foreign key (many2one)
    elif odoo_type == 'many2one':
        config['is_foreign_key'] = True
        config['indexed'] = True
        config['field_type'] = 'many2one'
        if 'relation' in field_def:
            config['related_model'] = field_def['relation']
    
    # Sync date field
    elif field_name in ('write_date', 'create_date'):
        config['is_sync_date'] = True
        config['indexed'] = True
    
    # Boolean fields
    elif odoo_type == 'boolean':
        config['nullable'] = True
    
    # Required fields
    elif field_def.get('required'):
        config['nullable'] = False
    
    return config


def generate_model_config(model: str, odoo_client: OdooClient) -> dict:
    """Generate complete model configuration from Odoo."""
    fields = odoo_client.get_model_fields(model)
    
    field_configs = []
    for field_name, field_def in fields.items():
        config = generate_field_config(field_name, field_def)
        if config:
            field_configs.append(config)
    
    # Generate table name from model name
    # e.g., purchase.order -> purchase_order
    table_name = model.replace('.', '_')
    
    return {
        'odoo_model': model,
        'postgres_table': table_name,
        'description': f"Auto-generated from {model}",
        'fields': field_configs,
    }


def generate_yaml(model: str, odoo_client: OdooClient) -> str:
    """Generate YAML config string for a model."""
    import yaml
    
    model_config = generate_model_config(model, odoo_client)
    
    # Build full config
    config = {
        'models': [model_config]
    }
    
    # Custom YAML representer for cleaner output
    def str_representer(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
    
    yaml.add_representer(str, str_representer)
    
    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main():
    parser = argparse.ArgumentParser(
        description='Auto-generate YAML config from Odoo fields_get()'
    )
    parser.add_argument(
        '--model', '-m',
        required=True,
        help='Odoo model technical name (e.g., purchase.order)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: print to stdout)'
    )
    parser.add_argument(
        '--all-fields',
        action='store_true',
        help='Include all fields, not just common ones'
    )
    
    args = parser.parse_args()
    
    # Get settings
    settings = get_settings()
    
    # Connect to Odoo
    print(f"Connecting to Odoo: {settings.odoo_url}", file=sys.stderr)
    client = OdooClient(
        url=settings.odoo_url,
        db=settings.odoo_db,
        username=settings.odoo_username,
        api_key=settings.odoo_api_key,
    )
    
    # Generate config
    print(f"Fetching fields for: {args.model}", file=sys.stderr)
    yaml_output = generate_yaml(args.model, client)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(yaml_output)
        print(f"Config written to: {args.output}", file=sys.stderr)
    else:
        print(yaml_output)


if __name__ == '__main__':
    main()