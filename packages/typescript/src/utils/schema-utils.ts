/**
 * Schema utilities for A2A Lite.
 *
 * Provides utilities for detecting and converting Zod schemas to JSON Schema.
 * Similar to Pydantic auto-detection in Python.
 */

import type { ZodTypeAny, ZodObject, ZodOptional, ZodDefault, ZodArray, ZodEnum, ZodUnion, ZodNullable, ZodRecord } from 'zod';

/**
 * Check if a value is a Zod schema.
 */
export function isZodSchema(value: unknown): value is ZodTypeAny {
  if (value === null || value === undefined) {
    return false;
  }
  
  // Zod schemas have various ways to detect them
  const obj = value as Record<string, unknown>;
  
  // Check for _def with typeName (some Zod versions) or type (other versions)
  if (obj._def && typeof obj._def === 'object' && obj._def !== null) {
    const def = obj._def as { typeName?: string; type?: string };
    // Check for Zod typeName
    if (def.typeName?.startsWith('Zod')) {
      return true;
    }
    // Check for newer Zod versions that use 'type' instead of 'typeName'
    if (def.type && ['string', 'number', 'boolean', 'object', 'array', 'enum', 'union', 'optional', 'nullable', 'default'].includes(def.type)) {
      return true;
    }
  }
  
  // Check for Zod-specific methods
  const methods = ['parse', 'parseAsync', 'safeParse', 'safeParseAsync', 'refine', 'transform'];
  const hasZodMethods = methods.every(method => typeof obj[method] === 'function');
  
  if (hasZodMethods) {
    return true;
  }
  
  return false;
}

/**
 * Get the type name from a Zod schema.
 */
function getZodTypeName(schema: unknown): string | undefined {
  const obj = schema as { _def?: { typeName?: string; type?: string } };
  return obj._def?.typeName || obj._def?.type;
}

/**
 * Helper to add description to schema result if present.
 */
function withDescription(schema: unknown, result: Record<string, unknown>): Record<string, unknown> {
  const s = schema as { description?: string };
  if (s.description) {
    result.description = s.description;
  }
  return result;
}

/**
 * Convert a Zod schema to JSON Schema.
 */
export function zodToJsonSchema(schema: ZodTypeAny): Record<string, unknown> {
  const typeName = getZodTypeName(schema);

  switch (typeName) {
    case 'ZodString':
    case 'string':
      return withDescription(schema, { type: 'string' });

    case 'ZodNumber':
    case 'number': {
      // Check if it's an integer
      const numSchema = schema as { _def?: { checks?: Array<{ def?: { format?: string }; isInt?: boolean }> } };
      const checks = numSchema._def?.checks ?? [];
      const isInt = checks.some((c) => c.def?.format === 'safeint' || c.isInt === true);
      return withDescription(schema, { type: isInt ? 'integer' : 'number' });
    }

    case 'ZodBoolean':
    case 'boolean':
      return withDescription(schema, { type: 'boolean' });

    case 'ZodNull':
    case 'null':
      return withDescription(schema, { type: 'null' });

    case 'ZodUndefined':
    case 'undefined':
      return { not: {} }; // undefined is not representable in JSON Schema

    case 'ZodAny':
    case 'ZodUnknown':
    case 'any':
    case 'unknown':
      return withDescription(schema, {});

    case 'ZodOptional':
    case 'optional': {
      const inner = (schema as { _def?: { innerType?: ZodTypeAny } })._def?.innerType
        || (schema as ZodOptional<ZodTypeAny>).unwrap?.();
      if (inner) {
        return zodToJsonSchema(inner);
      }
      return {};
    }

    case 'ZodNullable':
    case 'nullable': {
      const inner = (schema as { _def?: { innerType?: ZodTypeAny } })._def?.innerType
        || (schema as ZodNullable<ZodTypeAny>).unwrap?.();
      if (!inner) return {};
      const innerSchema = zodToJsonSchema(inner);
      const result: Record<string, unknown> = {};
      if (innerSchema.type && typeof innerSchema.type === 'string') {
        result.type = [innerSchema.type, 'null'];
      } else {
        result.anyOf = [innerSchema, { type: 'null' }];
      }
      if (innerSchema.description) {
        result.description = innerSchema.description;
      }
      return result;
    }

    case 'ZodDefault':
    case 'default': {
      const defSchema = schema as { _def?: { innerType?: ZodTypeAny; defaultValue?: unknown | (() => unknown) }; description?: string };
      const inner = defSchema._def?.innerType;
      if (!inner) return {};
      const innerJson = zodToJsonSchema(inner);
      const defaultValueRaw = defSchema._def?.defaultValue;
      const defaultValue = typeof defaultValueRaw === 'function' ? (defaultValueRaw as () => unknown)() : defaultValueRaw;
      const result: Record<string, unknown> = {
        ...innerJson,
        default: defaultValue,
      };
      // Add description if present
      if (defSchema.description) {
        result.description = defSchema.description;
      }
      return result;
    }

    case 'ZodArray':
    case 'array': {
      const arrSchema = schema as { _def?: { type?: ZodTypeAny; element?: ZodTypeAny } };
      // Handle both old (_def.type) and new (_def.element) Zod versions
      const element = arrSchema._def?.element || arrSchema._def?.type;
      if (!element) return withDescription(schema, { type: 'array' });
      const items = zodToJsonSchema(element);
      return withDescription(schema, {
        type: 'array',
        items,
      });
    }

    case 'ZodObject':
    case 'object': {
      const objSchema = schema as { shape?: Record<string, ZodTypeAny> | (() => Record<string, ZodTypeAny>); _def?: { shape?: Record<string, ZodTypeAny> | (() => Record<string, ZodTypeAny>) } };
      let shape: Record<string, ZodTypeAny> = {};

      // Handle both old (.shape() function) and new (_def.shape object) Zod versions
      if (objSchema.shape) {
        const s = objSchema.shape;
        shape = typeof s === 'function' ? s() : s;
      } else if (objSchema._def?.shape) {
        const s = objSchema._def.shape;
        shape = typeof s === 'function' ? s() : s;
      }

      const properties: Record<string, unknown> = {};
      const required: string[] = [];

      for (const [key, value] of Object.entries(shape)) {
        properties[key] = zodToJsonSchema(value);

        // Check if field is required (not optional and no default)
        const fieldTypeName = getZodTypeName(value);
        if (fieldTypeName !== 'ZodOptional' && fieldTypeName !== 'optional' &&
            fieldTypeName !== 'ZodDefault' && fieldTypeName !== 'default') {
          required.push(key);
        }
      }

      const result: Record<string, unknown> = {
        type: 'object',
        properties,
      };
      if (required.length > 0) {
        result.required = required;
      }
      return withDescription(schema, result);
    }

    case 'ZodEnum':
    case 'enum': {
      const enumSchema = schema as { _def?: { values?: string[]; entries?: Record<string, string> } };
      // Handle both old (_def.values) and new (_def.entries) Zod versions
      let values: string[] = [];
      if (enumSchema._def?.values) {
        values = enumSchema._def.values;
      } else if (enumSchema._def?.entries) {
        values = Object.values(enumSchema._def.entries);
      }
      return withDescription(schema, {
        type: 'string',
        enum: values,
      });
    }

    case 'ZodUnion':
    case 'union': {
      const unionSchema = schema as { _def?: { options?: ZodTypeAny[] } };
      const options = unionSchema._def?.options ?? [];
      return withDescription(schema, {
        anyOf: options.map((opt) => zodToJsonSchema(opt)),
      });
    }

    case 'ZodRecord':
    case 'record': {
      const recordSchema = schema as { _def?: { valueType?: ZodTypeAny; keyType?: ZodTypeAny } };
      // Handle both old (_def.valueType) and new (_def.keyType only) Zod versions
      const valueType = recordSchema._def?.valueType || recordSchema._def?.keyType;
      if (!valueType) return withDescription(schema, { type: 'object' });
      return withDescription(schema, {
        type: 'object',
        additionalProperties: zodToJsonSchema(valueType),
      });
    }

    case 'ZodLiteral':
    case 'literal': {
      const literalValue = (schema as { _def?: { value?: unknown } })._def?.value;
      return withDescription(schema, {
        const: literalValue,
      });
    }

    case 'ZodTuple':
    case 'tuple': {
      const tupleSchema = schema as { _def?: { items?: ZodTypeAny[] } };
      const items = tupleSchema._def?.items ?? [];
      return withDescription(schema, {
        type: 'array',
        items: items.map((item) => zodToJsonSchema(item)),
        minItems: items.length,
        maxItems: items.length,
      });
    }

    case 'ZodDate':
    case 'date':
      return withDescription(schema, {
        type: 'string',
        format: 'date-time',
      });

    default: {
      // Handle ZodEffects (refinements, transforms) by unwrapping
      if (typeName === 'ZodEffects' || typeName === 'effects') {
        const effectSchema = schema as { _def?: { schema?: ZodTypeAny } };
        const inner = effectSchema._def?.schema;
        if (inner) {
          return zodToJsonSchema(inner);
        }
      }

      // Handle ZodPipeline by getting the input schema
      if (typeName === 'ZodPipeline' || typeName === 'pipeline') {
        const pipeSchema = schema as { _def?: { in?: ZodTypeAny } };
        const inner = pipeSchema._def?.in;
        if (inner) {
          return zodToJsonSchema(inner);
        }
      }

      // Fallback for unknown types
      return withDescription(schema, {});
    }
  }
}

/**
 * Extract Zod schemas from function parameters.
 * Returns a map of parameter names to their JSON schemas.
 */
export function extractZodSchemas(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  schemas: Record<string, any>
): Record<string, Record<string, unknown>> {
  const result: Record<string, Record<string, unknown>> = {};
  
  for (const [key, value] of Object.entries(schemas)) {
    if (isZodSchema(value)) {
      result[key] = zodToJsonSchema(value);
    }
  }
  
  return result;
}
