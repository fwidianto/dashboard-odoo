"""PostgreSQL identifier generation utilities.

This module provides centralized identifier generation for PostgreSQL schema objects
including tables, columns, indexes, constraints, and sequences.

Key features:
- Deterministic generation (same inputs always produce same outputs)
- Collision-safe hash suffixes
- Guaranteed PostgreSQL identifier compliance (max 63 chars)
- Readable prefixes for debugging

PostgreSQL identifier limits:
- Maximum 63 characters
- Must start with a letter or underscore
- Can only contain letters, digits, and underscores
- Reserved keywords should be avoided

Example usage:
    >>> from src.utils.identifier import generate_safe_identifier
    >>> generate_safe_identifier("idx", "purchase_order_line", "x_studio_approval_request_receipt_location")
    'idx_purchase_order_line_x_studio_appr_a1b2c3'
"""

import hashlib
import re
from typing import Optional

from src.utils.logging import get_logger

# PostgreSQL reserved keywords that should be avoided in identifiers
# This list focuses on words that will cause immediate SQL parsing errors
# when used as identifiers without quotes.
# NOTE: Common Odoo field names like 'id', 'name', 'type' are NOT included
# because Odoo uses them frequently and they work fine as column names.
RESERVED_KEYWORDS = frozenset([
    # SQL standard reserved words (those that ALWAYS cause parsing errors)
    'all', 'analyse', 'analyze', 'and', 'any', 'array', 'as', 'asc',
    'asymmetric', 'authorization', 'both', 'case', 'cast', 'check',
    'collate', 'collation', 'column', 'concurrently', 'constraint',
    'create', 'cross', 'current_catalog', 'current_date', 'current_role',
    'current_schema', 'current_time', 'current_timestamp', 'current_user',
    'default', 'deferrable', 'desc', 'distinct', 'do', 'else', 'end',
    'except', 'false', 'fetch', 'for', 'foreign', 'from', 'full', 'grant',
    'group', 'having', 'ilike', 'in', 'initially', 'inner', 'intersect',
    'into', 'is', 'isnull', 'join', 'lateral', 'leading', 'left', 'like',
    'limit', 'localtime', 'localtimestamp', 'natural', 'not', 'notnull',
    'null', 'offset', 'on', 'only', 'or', 'order', 'outer', 'overlaps',
    'placing', 'primary', 'references', 'returning', 'right', 'select',
    'session_user', 'similar', 'some', 'symmetric', 'table', 'tablesample',
    'then', 'to', 'trailing', 'true', 'union', 'unique', 'user', 'using',
    'variadic', 'verbose', 'when', 'where', 'window', 'with',
    # PostgreSQL-specific type keywords (only when used standalone)
    'bigint', 'bigserial', 'bit', 'boolean', 'box', 'char', 'character',
    'cidr', 'circle', 'citext', 'date', 'decimal', 'double', 'float',
    'inet', 'int', 'integer', 'interval', 'json', 'jsonb', 'line', 'lseg',
    'macaddr', 'money', 'numeric', 'path', 'point', 'polygon', 'real',
    'serial', 'serial8', 'smallint', 'smallserial', 'text', 'time',
    'timestamp', 'timestamptz', 'timetz', 'tsquery', 'tsvector', 'txid_snapshot',
    'uuid', 'varchar', 'xml',
])

# PostgreSQL maximum identifier length
MAX_IDENTIFIER_LENGTH = 63

# Minimum characters reserved for hash suffix
MIN_HASH_SUFFIX_LENGTH = 8

# Characters to use in hash suffix (alphanumeric for readability)
HASH_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz'


def _sanitize_name(name: str) -> str:
    """
    Sanitize a name to be a valid PostgreSQL identifier.
    
    - Converts to lowercase
    - Replaces invalid characters with underscores
    - Ensures starts with letter or underscore
    
    Args:
        name: The name to sanitize
        
    Returns:
        Sanitized name safe for PostgreSQL
    """
    if not name:
        return "_"
    
    # Convert to lowercase
    sanitized = name.lower()
    
    # Replace invalid characters with underscores
    # PostgreSQL allows only: letters, digits, underscores, and dollar sign
    sanitized = re.sub(r'[^a-z0-9_]', '_', sanitized)
    
    # Ensure starts with letter or underscore (not digit)
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized
    
    # Collapse consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    return sanitized or "_"


def _generate_deterministic_hash(*parts: str) -> str:
    """
    Generate a deterministic short hash from input parts.
    
    Uses MD5 for speed and consistency. Takes first 8 characters
    of the hash for collision safety while keeping identifiers readable.
    
    Args:
        *parts: Variable number of string parts to hash
        
    Returns:
        8-character hexadecimal hash string
    """
    combined = '_'.join(str(p) for p in parts if p)
    hash_bytes = hashlib.md5(combined.encode('utf-8')).digest()
    return ''.join(HASH_CHARS[c % len(HASH_CHARS)] for c in hash_bytes[:8])


def generate_safe_identifier(
    prefix: str,
    table_name: str,
    column_name: str,
    max_length: int = MAX_IDENTIFIER_LENGTH,
    extra_suffix: Optional[str] = None,
) -> str:
    """
    Generate a safe PostgreSQL identifier that won't exceed length limits.
    
    The generated identifier has the format:
        {prefix}_{table_name}_{column_name}_{hash}
    
    If the total length exceeds max_length, the identifier is truncated
    from the right and a deterministic hash is appended to ensure uniqueness.
    
    The hash is deterministic based on the full original components,
    ensuring the same inputs always produce the same output.
    
    Args:
        prefix: Identifier prefix (e.g., 'idx', 'fk', 'uq', 'ck')
        table_name: Name of the table
        column_name: Name of the column or additional context
        max_length: Maximum identifier length (default: 63 for PostgreSQL)
        extra_suffix: Optional extra suffix for disambiguation
        
    Returns:
        Safe identifier string that:
        - Is <= max_length characters
        - Contains a readable prefix
        - Has a deterministic hash suffix for uniqueness
        
    Example:
        >>> generate_safe_identifier("idx", "purchase_order_line", "x_studio_approval_request_receipt_location")
        'idx_purchase_order_line_x_studio_appr_a1b2c3d4'
        
        >>> generate_safe_identifier("idx", "very_long_table_name", "very_long_column_name_that_exceeds_limit")
        'idx_very_long_table_name_very_long_col_ab12cd34'
    """
    # Sanitize all inputs
    prefix = _sanitize_name(prefix)
    table = _sanitize_name(table_name)
    column = _sanitize_name(column_name)
    
    # Build full identifier base (without hash)
    base_parts = [prefix, table, column]
    if extra_suffix:
        base_parts.append(_sanitize_name(extra_suffix))
    
    full_base = '_'.join(p for p in base_parts if p)
    
    # If within limit, return as-is
    if len(full_base) <= max_length:
        # Check for reserved keyword conflicts
        identifier = full_base
        if identifier.lower() in RESERVED_KEYWORDS:
            identifier = f"{identifier}_x"
        return identifier
    
    # Need to truncate and add hash
    # Reserve space for hash suffix + separator
    hash_length = MIN_HASH_SUFFIX_LENGTH
    available_length = max_length - 1 - hash_length  # -1 for underscore before hash
    
    # Generate deterministic hash from full original base
    hash_suffix = _generate_deterministic_hash(prefix, table_name, column_name, extra_suffix or "")
    
    # Truncate the base to fit, keeping prefix and table if possible
    # Strategy: Keep prefix_table, truncate column, add hash
    
    # Calculate minimum prefix_table length
    prefix_table = f"{prefix}_{table}"
    min_prefix_len = len(prefix_table)
    
    if available_length <= min_prefix_len:
        # Extremely constrained - truncate prefix_table
        truncated = full_base[:available_length]
    else:
        # Keep prefix_table + portion of column
        truncated = f"{prefix_table}_{column}"[:available_length]
    
    # Final identifier
    identifier = f"{truncated}_{hash_suffix}"
    
    # Double-check length (defensive)
    if len(identifier) > max_length:
        identifier = identifier[:max_length]
    
    # Check for reserved keyword conflicts (can happen after truncation)
    if identifier.lower() in RESERVED_KEYWORDS:
        # Add _x suffix if space allows, otherwise truncate and add suffix
        available = max_length - len("_x")
        if len(identifier) <= available:
            identifier = f"{identifier}_x"
        else:
            identifier = f"{identifier[:available]}_x"
    
    return identifier


def generate_table_name(odoo_model: str) -> str:
    """
    Generate a safe PostgreSQL table name from an Odoo model name.
    
    Args:
        odoo_model: Odoo model technical name (e.g., 'purchase.order.line')
        
    Returns:
        Safe table name (e.g., 'purchase_order_line')
        
    Example:
        >>> generate_table_name("res.partner")
        'res_partner'
        >>> generate_table_name("sale.order")
        'sale_order'
    """
    # Replace dots with underscores
    sanitized = odoo_model.replace('.', '_')
    sanitized = _sanitize_name(sanitized)
    
    # Truncate if necessary to fit within PostgreSQL limit
    if len(sanitized) > MAX_IDENTIFIER_LENGTH:
        # Generate hash from original name for determinism
        hash_suffix = _generate_deterministic_hash(odoo_model)
        available = MAX_IDENTIFIER_LENGTH - 1 - len(hash_suffix)
        sanitized = f"{sanitized[:available]}_{hash_suffix}"
    
    return sanitized


def generate_column_name(odoo_field: str) -> str:
    """
    Generate a safe PostgreSQL column name from an Odoo field name.
    
    Args:
        odoo_field: Odoo field name
        
    Returns:
        Safe column name that won't exceed PostgreSQL identifier limits
        
    Example:
        >>> generate_column_name("x_studio_approval_request_receipt_location")
        'x_studio_approval_request_receipt_location'
    """
    sanitized = _sanitize_name(odoo_field)
    
    # Truncate if necessary to fit within PostgreSQL limit
    # Use generate_safe_identifier for consistent handling
    if len(sanitized) > MAX_IDENTIFIER_LENGTH:
        # Generate hash from original name for determinism
        hash_suffix = _generate_deterministic_hash(odoo_field)
        available = MAX_IDENTIFIER_LENGTH - 1 - len(hash_suffix)
        return f"{sanitized[:available]}_{hash_suffix}"
    
    # Check for reserved keyword conflicts
    if sanitized.lower() in RESERVED_KEYWORDS:
        return f"{sanitized}_x"
    
    return sanitized


def generate_index_name(
    table_name: str,
    column_name: str,
    index_type: Optional[str] = None,
) -> str:
    """
    Generate a safe PostgreSQL index name.
    
    Args:
        table_name: Name of the indexed table
        column_name: Name of the indexed column
        index_type: Optional index type ('btree', 'hash', etc.)
        
    Returns:
        Safe index name
        
    Example:
        >>> generate_index_name("purchase_order_line", "x_studio_approval_request_receipt_location")
        'idx_purchase_order_line_x_studio_appr_a1b2c3d4'
    """
    prefix = "idx"
    if index_type and index_type.lower() != 'btree':
        prefix = f"idx_{index_type}"
    
    return generate_safe_identifier(prefix, table_name, column_name)


def generate_primary_key_name(table_name: str) -> str:
    """
    Generate a safe PostgreSQL primary key constraint name.
    
    Args:
        table_name: Name of the table
        
    Returns:
        Safe primary key constraint name
        
    Example:
        >>> generate_primary_key_name("res_partner")
        'res_partner_pkey'
    """
    sanitized = _sanitize_name(table_name)
    name = f"{sanitized}_pkey"
    
    # Truncate if necessary (pkey suffix is short)
    if len(name) > MAX_IDENTIFIER_LENGTH:
        hash_suffix = _generate_deterministic_hash(table_name, "pkey")
        max_table_len = MAX_IDENTIFIER_LENGTH - 1 - len(hash_suffix)
        return f"{sanitized[:max_table_len]}_{hash_suffix}"
    
    return name


def generate_foreign_key_name(
    table_name: str,
    column_name: str,
    foreign_table: str,
) -> str:
    """
    Generate a safe PostgreSQL foreign key constraint name.
    
    Args:
        table_name: Name of the referencing table
        column_name: Name of the referencing column
        foreign_table: Name of the referenced table
        
    Returns:
        Safe foreign key constraint name
        
    Example:
        >>> generate_foreign_key_name("sale_order_line", "partner_id", "res_partner")
        'fk_sale_order_line_partner_id_a1b2c3d4'
    """
    return generate_safe_identifier(
        "fk",
        table_name,
        column_name,
        extra_suffix=foreign_table,
    )


def generate_unique_constraint_name(
    table_name: str,
    column_names: list[str],
) -> str:
    """
    Generate a safe PostgreSQL unique constraint name.
    
    Args:
        table_name: Name of the table
        column_names: List of column names in the constraint
        
    Returns:
        Safe unique constraint name
        
    Example:
        >>> generate_unique_constraint_name("res_partner", ["company_id", "vat"])
        'uq_res_partner_company_id_vat_a1b2c3d4'
    """
    combined_columns = "_".join(column_names)
    return generate_safe_identifier(
        "uq",
        table_name,
        combined_columns,
    )


def generate_check_constraint_name(
    table_name: str,
    condition_description: str,
) -> str:
    """
    Generate a safe PostgreSQL check constraint name.
    
    Args:
        table_name: Name of the table
        condition_description: Description of the check condition
        
    Returns:
        Safe check constraint name
        
    Example:
        >>> generate_check_constraint_name("res_partner", "positive_balance")
        'ck_res_partner_positive_balance_a1b2c3d4'
    """
    # Hash the condition to keep name short
    hash_suffix = _generate_deterministic_hash(table_name, condition_description)
    base = f"ck_{_sanitize_name(table_name)}_{_sanitize_name(condition_description)}"
    
    if len(base) > MAX_IDENTIFIER_LENGTH:
        max_base_len = MAX_IDENTIFIER_LENGTH - 1 - len(hash_suffix)
        return f"{base[:max_base_len]}_{hash_suffix}"
    
    return base


def generate_sequence_name(table_name: str, column_name: str) -> str:
    """
    Generate a safe PostgreSQL sequence name.
    
    Args:
        table_name: Name of the table
        column_name: Name of the column
        
    Returns:
        Safe sequence name
        
    Example:
        >>> generate_sequence_name("res_partner", "id")
        'seq_res_partner_id'
    """
    return generate_safe_identifier("seq", table_name, column_name)


def validate_identifier(identifier: str) -> tuple[bool, Optional[str]]:
    """
    Validate a PostgreSQL identifier for compliance.
    
    Checks:
    - Length <= 63 characters
    - Starts with letter or underscore
    - Contains only valid characters
    - Not a reserved keyword
    
    Args:
        identifier: The identifier to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        error_message is None if valid
        
    Example:
        >>> validate_identifier("valid_name")
        (True, None)
        >>> validate_identifier("123invalid")
        (False, 'Identifier must start with a letter or underscore')
        >>> validate_identifier("a" * 64)
        (False, 'Identifier exceeds 63 characters')
    """
    if not identifier:
        return False, "Identifier cannot be empty"
    
    # Check length
    if len(identifier) > MAX_IDENTIFIER_LENGTH:
        return False, f"Identifier exceeds {MAX_IDENTIFIER_LENGTH} characters (got {len(identifier)})"
    
    # Check starts with letter or underscore
    if not re.match(r'^[a-z_]', identifier, re.IGNORECASE):
        return False, "Identifier must start with a letter or underscore"
    
    # Check valid characters
    if not re.match(r'^[a-z_][a-z0-9_]*$', identifier, re.IGNORECASE):
        return False, "Identifier contains invalid characters (only letters, digits, and underscores allowed)"
    
    # Check reserved keywords
    if identifier.lower() in RESERVED_KEYWORDS:
        return False, f"Identifier '{identifier}' is a PostgreSQL reserved keyword"
    
    return True, None


def validate_schema_identifiers(
    table_name: str,
    column_names: list[str],
    index_names: list[str],
    constraint_names: list[str],
) -> list[str]:
    """
    Validate all identifiers for a schema definition.
    
    Use this before creating tables, indexes, or constraints
    to ensure all names are PostgreSQL-compliant.
    
    Args:
        table_name: Proposed table name
        column_names: Proposed column names
        index_names: Proposed index names
        constraint_names: Proposed constraint names
        
    Returns:
        List of validation errors (empty if all valid)
    """
    errors = []
    
    # Validate table name
    valid, error = validate_identifier(table_name)
    if not valid:
        errors.append(f"Table name '{table_name}': {error}")
    
    # Validate column names
    seen_columns = set()
    for col in column_names:
        valid, error = validate_identifier(col)
        if not valid:
            errors.append(f"Column name '{col}': {error}")
        if col.lower() in seen_columns:
            errors.append(f"Duplicate column name '{col}'")
        seen_columns.add(col.lower())
    
    # Validate index names
    seen_indexes = set()
    for idx in index_names:
        valid, error = validate_identifier(idx)
        if not valid:
            errors.append(f"Index name '{idx}': {error}")
        if idx.lower() in seen_indexes:
            errors.append(f"Duplicate index name '{idx}'")
        seen_indexes.add(idx.lower())
    
    # Validate constraint names
    seen_constraints = set()
    for constraint in constraint_names:
        valid, error = validate_identifier(constraint)
        if not valid:
            errors.append(f"Constraint name '{constraint}': {error}")
        if constraint.lower() in seen_constraints:
            errors.append(f"Duplicate constraint name '{constraint}'")
        seen_constraints.add(constraint.lower())
    
    return errors


class IdentifierGenerator:
    """
    Stateful identifier generator for complex schema generation scenarios.
    
    Use this class when generating multiple related identifiers to ensure
    consistency and detect potential collisions.
    
    Example:
        >>> gen = IdentifierGenerator()
        >>> gen.generate_index_name("users", "email")
        'idx_users_email_a1b2c3d4'
        >>> gen.generate_index_name("users", "email")  # Same call, same result
        'idx_users_email_a1b2c3d4'
    """
    
    def __init__(self, max_length: int = MAX_IDENTIFIER_LENGTH):
        self.max_length = max_length
        self._logger = get_logger("identifier_generator")
        self._generated: dict[str, int] = {}  # Track generated identifiers
    
    def generate(
        self,
        prefix: str,
        table_name: str,
        column_name: str,
        extra_suffix: Optional[str] = None,
    ) -> str:
        """Generate a safe identifier and track it."""
        identifier = generate_safe_identifier(
            prefix=prefix,
            table_name=table_name,
            column_name=column_name,
            max_length=self.max_length,
            extra_suffix=extra_suffix,
        )
        self._track(identifier)
        return identifier
    
    def generate_index(
        self,
        table_name: str,
        column_name: str,
        index_type: Optional[str] = None,
    ) -> str:
        """Generate a safe index name."""
        identifier = generate_index_name(table_name, column_name, index_type)
        self._track(identifier)
        return identifier
    
    def generate_primary_key(self, table_name: str) -> str:
        """Generate a safe primary key name."""
        identifier = generate_primary_key_name(table_name)
        self._track(identifier)
        return identifier
    
    def generate_foreign_key(
        self,
        table_name: str,
        column_name: str,
        foreign_table: str,
    ) -> str:
        """Generate a safe foreign key name."""
        identifier = generate_foreign_key_name(table_name, column_name, foreign_table)
        self._track(identifier)
        return identifier
    
    def generate_unique_constraint(
        self,
        table_name: str,
        column_names: list[str],
    ) -> str:
        """Generate a safe unique constraint name."""
        identifier = generate_unique_constraint_name(table_name, column_names)
        self._track(identifier)
        return identifier
    
    def generate_check_constraint(
        self,
        table_name: str,
        condition: str,
    ) -> str:
        """Generate a safe check constraint name."""
        identifier = generate_check_constraint_name(table_name, condition)
        self._track(identifier)
        return identifier
    
    def _track(self, identifier: str) -> None:
        """Track a generated identifier for collision detection."""
        lower_id = identifier.lower()
        self._generated[lower_id] = self._generated.get(lower_id, 0) + 1
    
    def has_collisions(self) -> bool:
        """Check if any identifiers were generated multiple times."""
        return any(count > 1 for count in self._generated.values())
    
    def get_duplicates(self) -> list[str]:
        """Get list of identifiers that were generated multiple times."""
        return [
            identifier
            for identifier, count in self._generated.items()
            if count > 1
        ]
    
    def validate_all(self) -> list[str]:
        """
        Validate all generated identifiers.
        
        Returns:
            List of validation errors
        """
        errors = []
        for identifier in self._generated:
            valid, error = validate_identifier(identifier)
            if not valid:
                errors.append(f"{identifier}: {error}")
        return errors
