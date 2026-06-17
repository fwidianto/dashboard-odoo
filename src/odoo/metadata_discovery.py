"""Odoo Metadata Discovery Module.

This module provides automatic schema discovery from Odoo's metadata system.
It retrieves field definitions using:
1. ir.model.fields - for stored field metadata
2. fields_get() - for detailed field information

Only fields with store=True are synchronized, as non-stored computed fields
cannot be reliably synchronized.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.clients.odoo_client import OdooClient


@dataclass
class OdooField:
    """Represents a single Odoo field definition."""
    
    name: str
    field_type: str
    string: str
    required: bool = False
    readonly: bool = False
    store: bool = True
    index: bool = False
    relation: Optional[str] = None
    size: Optional[int] = None
    help: Optional[str] = None
    selection: Optional[list] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "field_type": self.field_type,
            "string": self.string,
            "required": self.required,
            "readonly": self.readonly,
            "store": self.store,
            "index": self.index,
            "relation": self.relation,
            "size": self.size,
            "help": self.help,
        }


@dataclass
class OdooModelMetadata:
    """Metadata for an entire Odoo model."""
    
    model: str
    table: str
    fields: dict = field(default_factory=dict)
    field_count: int = 0
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    metadata_hash: str = ""
    
    def get_stored_fields(self) -> dict:
        """Get only stored fields (store=True)."""
        return {name: f for name, f in self.fields.items() if f.store}
    
    def get_field_count(self) -> int:
        """Get count of stored fields."""
        return len(self.get_stored_fields())
    
    def compute_hash(self) -> str:
        """Compute hash of metadata for caching."""
        field_data = {
            name: f.to_dict() 
            for name, f in self.fields.items()
            if f.store
        }
        hash_input = json.dumps(field_data, sort_keys=True)
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "table": self.table,
            "field_count": self.get_field_count(),
            "discovered_at": self.discovered_at.isoformat(),
            "metadata_hash": self.metadata_hash,
            "fields": {
                name: f.to_dict() 
                for name, f in self.fields.items()
                if f.store
            },
        }


@dataclass
class SchemaCache:
    """Schema cache for performance optimization."""
    
    cache_file: str = "schema_cache.json"
    entries: dict = field(default_factory=dict)
    
    def load(self) -> bool:
        """Load cache from disk."""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                self.entries = json.load(f)
            get_logger("schema_cache").info(
                "Schema cache loaded",
                entries=len(self.entries),
            )
            return True
        except Exception as e:
            get_logger("schema_cache").warning(
                "Failed to load schema cache",
                error=str(e),
            )
            return False
    
    def save(self) -> None:
        """Save cache to disk."""
        cache_dir = os.path.dirname(self.cache_file)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        
        with open(self.cache_file, 'w') as f:
            json.dump(self.entries, f, indent=2)
        
        get_logger("schema_cache").info(
            "Schema cache saved",
            entries=len(self.entries),
        )
    
    def get(self, model: str) -> Optional[dict]:
        """Get cached entry for a model."""
        return self.entries.get(model)
    
    def set(self, model: str, metadata: OdooModelMetadata) -> None:
        """Set cached entry for a model."""
        self.entries[model] = {
            "model": metadata.model,
            "table": metadata.table,
            "field_count": metadata.get_field_count(),
            "discovered_at": metadata.discovered_at.isoformat(),
            "metadata_hash": metadata.metadata_hash,
        }
    
    def needs_update(self, model: str, new_hash: str) -> bool:
        """Check if a model needs schema update."""
        if model not in self.entries:
            return True
        
        cached = self.entries[model]
        return cached.get("metadata_hash") != new_hash


class OdooMetadataDiscovery:
    """
    Automatic Odoo schema discovery.
    
    Retrieves field definitions from Odoo's metadata system and converts
    them to PostgreSQL-compatible schema definitions.
    """
    
    # Odoo field type to PostgreSQL type mapping
    ODOO_TO_POSTGRES_TYPE = {
        'integer': 'BIGINT',
        'bigint': 'BIGINT',
        'float': 'NUMERIC(30,10)',
        'monetary': 'NUMERIC(30,10)',
        'boolean': 'BOOLEAN',
        'char': 'TEXT',
        'text': 'TEXT',
        'html': 'TEXT',
        'selection': 'TEXT',
        'reference': 'TEXT',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'many2one': 'BIGINT',
        'one2many': 'JSONB',
        'many2many': 'JSONB',
        'binary': 'TEXT',
        'unknown': 'TEXT',
    }
    
    # Relational field types stored as JSONB
    RELATIONAL_TYPES = frozenset(['one2many', 'many2many'])
    
    # System fields to skip
    SYSTEM_FIELDS = frozenset(['__last_update'])
    
    def __init__(self, odoo_client: Optional["OdooClient"] = None):
        """Initialize metadata discovery."""
        self._client = odoo_client
        self._logger = get_logger("metadata_discovery")
        self._cache = SchemaCache()
    
    def discover_model(self, model: str, use_cache: bool = True) -> OdooModelMetadata:
        """Discover metadata for a single model."""
        table = self._model_to_table(model)
        metadata = OdooModelMetadata(model=model, table=table)
        
        if use_cache:
            self._cache.load()
            cached = self._cache.get(model)
            if cached:
                self._logger.info(
                    "Using cached schema",
                    model=model,
                    field_count=cached.get("field_count", 0),
                )
        
        self._discover_fields(model, metadata)
        metadata.metadata_hash = metadata.compute_hash()
        self._cache.set(model, metadata)
        self._cache.save()
        
        self._logger.info(
            "Model metadata discovered",
            model=model,
            table=table,
            stored_fields=metadata.get_field_count(),
            total_fields=len(metadata.fields),
        )
        
        return metadata
    
    def discover_models(
        self, 
        models: list, 
        use_cache: bool = True
    ) -> dict:
        """Discover metadata for multiple models."""
        results = {}
        
        if use_cache:
            self._cache.load()
        
        for model in models:
            try:
                metadata = self.discover_model(model, use_cache=False)
                results[model] = metadata
            except Exception as e:
                self._logger.error(
                    "Failed to discover model",
                    model=model,
                    error=str(e),
                )
        
        if use_cache and results:
            for model, metadata in results.items():
                self._cache.set(model, metadata)
            self._cache.save()
        
        return results
    
    def _discover_fields(self, model: str, metadata: OdooModelMetadata) -> None:
        """Discover all fields for a model using Odoo's metadata APIs."""
        if self._client is None:
            self._logger.warning(
                "No Odoo client available, using empty metadata",
                model=model,
            )
            return
        
        try:
            fields_data = self._client.execute(
                'fields_get',
                [model],
                attributes=[
                    'name', 'type', 'string', 'required', 'readonly',
                    'store', 'index', 'relation', 'size', 'help', 'selection',
                ],
            )
            
            for field_name, field_info in fields_data.items():
                if field_name in self.SYSTEM_FIELDS:
                    continue
                
                field = self._parse_field_definition(field_name, field_info)
                if field:
                    metadata.fields[field_name] = field
                    
        except Exception as e:
            self._logger.warning(
                "fields_get failed, trying alternative method",
                model=model,
                error=str(e),
            )
            self._discover_from_ir_model_fields(model, metadata)
    
    def _discover_from_ir_model_fields(
        self, 
        model: str, 
        metadata: OdooModelMetadata
    ) -> None:
        """Fallback: Discover fields from ir.model.fields."""
        if self._client is None:
            return
        
        try:
            field_ids = self._client.execute(
                'search_read',
                'ir.model.fields',
                [['model', '=', model], ['store', '=', True]],
                [
                    'name', 'field_description', 'ttype', 'required', 'readonly',
                    'index', 'relation', 'field_length',
                ],
            )
            
            for field_def in field_ids:
                fld = OdooField(
                    name=field_def['name'],
                    field_type=field_def['ttype'],
                    string=field_def.get('field_description', ''),
                    required=field_def.get('required', False),
                    readonly=field_def.get('readonly', False),
                    store=True,
                    index=field_def.get('index', False),
                    relation=field_def.get('relation'),
                    size=field_def.get('field_length'),
                )
                metadata.fields[fld.name] = fld
                
        except Exception as e:
            self._logger.error(
                "ir.model.fields discovery failed",
                model=model,
                error=str(e),
            )
            raise
    
    def _parse_field_definition(
        self, 
        field_name: str, 
        field_info: dict
    ) -> Optional[OdooField]:
        """Parse a field definition from fields_get response."""
        field_type = field_info.get('type', 'unknown')
        
        store = field_info.get('store', True)
        if not store:
            return None
        
        relation = None
        if field_type in ['many2one', 'many2many', 'one2many']:
            relation = field_info.get('relation')
        
        selection = field_info.get('selection')
        
        return OdooField(
            name=field_name,
            field_type=field_type,
            string=field_info.get('string', ''),
            required=field_info.get('required', False),
            readonly=field_info.get('readonly', False),
            store=store,
            index=field_info.get('index', False),
            relation=relation,
            size=field_info.get('size'),
            help=field_info.get('help'),
            selection=selection if isinstance(selection, list) else None,
        )
    
    def _model_to_table(self, model: str) -> str:
        """Convert Odoo model name to PostgreSQL table name."""
        return model.replace('.', '_').lower()
    
    def get_postgres_type(self, odoo_type: str) -> str:
        """Get PostgreSQL type for an Odoo field type."""
        return self.ODOO_TO_POSTGRES_TYPE.get(
            odoo_type, 
            self.ODOO_TO_POSTGRES_TYPE['unknown']
        )
    
    def is_relational_type(self, odoo_type: str) -> bool:
        """Check if field type is relational (one2many, many2many)."""
        return odoo_type in self.RELATIONAL_TYPES
    
    def is_syncable(self, fld: OdooField) -> bool:
        """Check if a field should be synchronized."""
        return (
            fld.store and
            fld.name not in self.SYSTEM_FIELDS
        )


def generate_field_configs(metadata: OdooModelMetadata) -> list:
    """Generate field configurations from discovered metadata."""
    discovery = OdooMetadataDiscovery(None)
    
    configs = []
    
    for name, fld in metadata.fields.items():
        if not discovery.is_syncable(fld):
            continue
        
        postgres_type = discovery.get_postgres_type(fld.field_type)
        is_relational = discovery.is_relational_type(fld.field_type)
        
        # Determine field type for config
        if fld.field_type == 'many2one':
            config_field_type = 'many2one'
        elif is_relational:
            config_field_type = fld.field_type
        else:
            config_field_type = 'basic'
        
        config = {
            'odoo_field': name,
            'postgres_column': name.replace('.', '_'),
            'postgres_type': postgres_type,
            'field_type': config_field_type,
            'required': fld.required,
            'indexed': fld.index,
        }
        
        if fld.relation:
            config['related_model'] = fld.relation
        
        # Add default value for required fields
        if fld.required and not fld.readonly:
            if fld.field_type in ['integer', 'bigint']:
                config['default_value'] = 0
            elif fld.field_type in ['float', 'monetary']:
                config['default_value'] = 0.0
            elif fld.field_type == 'boolean':
                config['default_value'] = False
            elif fld.field_type in ['char', 'text', 'html', 'selection', 'reference']:
                config['default_value'] = ''
        
        configs.append(config)
    
    return configs
