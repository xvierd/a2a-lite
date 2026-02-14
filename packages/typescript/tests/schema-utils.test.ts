import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { Agent } from '../src/index.js';
import { isZodSchema, zodToJsonSchema } from '../src/utils/schema-utils.js';

describe('Zod Schema Detection', () => {
  describe('isZodSchema', () => {
    it('should detect Zod schemas', () => {
      const stringSchema = z.string();
      const objectSchema = z.object({ name: z.string() });
      
      expect(isZodSchema(stringSchema)).toBe(true);
      expect(isZodSchema(objectSchema)).toBe(true);
    });

    it('should return false for non-Zod values', () => {
      expect(isZodSchema('string')).toBe(false);
      expect(isZodSchema(123)).toBe(false);
      expect(isZodSchema({})).toBe(false);
      expect(isZodSchema(null)).toBe(false);
      expect(isZodSchema(undefined)).toBe(false);
      expect(isZodSchema(() => {})).toBe(false);
    });

    it('should handle edge cases', () => {
      expect(isZodSchema([])).toBe(false);
      expect(isZodSchema(new Date())).toBe(false);
      expect(isZodSchema(/regex/)).toBe(false);
    });
  });

  describe('zodToJsonSchema', () => {
    it('should convert string schema', () => {
      const schema = z.string();
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({ type: 'string' });
    });

    it('should convert number schema', () => {
      const schema = z.number();
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({ type: 'number' });
    });

    it('should convert boolean schema', () => {
      const schema = z.boolean();
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({ type: 'boolean' });
    });

    it('should convert integer schema', () => {
      const schema = z.number().int();
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({ type: 'integer' });
    });

    it('should convert object schema', () => {
      const schema = z.object({
        name: z.string(),
        age: z.number(),
      });
      
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
        },
        required: ['name', 'age'],
      });
    });

    it('should handle optional fields', () => {
      const schema = z.object({
        name: z.string(),
        age: z.number().optional(),
      });
      
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
        },
        required: ['name'],
      });
    });

    it('should handle array schema', () => {
      const schema = z.array(z.string());
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'array',
        items: { type: 'string' },
      });
    });

    it('should handle enum schema', () => {
      const schema = z.enum(['a', 'b', 'c']);
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'string',
        enum: ['a', 'b', 'c'],
      });
    });

    it('should handle union schema', () => {
      const schema = z.union([z.string(), z.number()]);
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        anyOf: [
          { type: 'string' },
          { type: 'number' },
        ],
      });
    });

    it('should handle default values', () => {
      const schema = z.object({
        name: z.string().default('Anonymous'),
      });
      
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string', default: 'Anonymous' },
        },
        // required field omitted when empty
      });
    });

    it('should handle nullable', () => {
      const schema = z.string().nullable();
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: ['string', 'null'],
      });
    });

    it('should handle descriptions', () => {
      const schema = z.object({
        name: z.string().describe('The user name'),
      });
      
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          name: { type: 'string', description: 'The user name' },
        },
        required: ['name'],
      });
    });

    it('should handle nested objects', () => {
      const schema = z.object({
        user: z.object({
          name: z.string(),
          email: z.string(),
        }),
      });
      
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'object',
        properties: {
          user: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              email: { type: 'string' },
            },
            required: ['name', 'email'],
          },
        },
        required: ['user'],
      });
    });

    it('should handle record types', () => {
      const schema = z.record(z.string());
      const jsonSchema = zodToJsonSchema(schema);
      
      expect(jsonSchema).toEqual({
        type: 'object',
        additionalProperties: { type: 'string' },
      });
    });
  });

  describe('Integration', () => {
    it('should work with complex schemas', () => {
      const UserSchema = z.object({
        id: z.number().int(),
        name: z.string().min(1).max(100),
        email: z.string().email(),
        age: z.number().int().min(0).max(150).optional(),
        roles: z.array(z.enum(['user', 'admin', 'moderator'])),
        metadata: z.record(z.unknown()).optional(),
      });
      
      const jsonSchema = zodToJsonSchema(UserSchema);
      
      expect(jsonSchema.type).toBe('object');
      expect(jsonSchema.properties).toBeDefined();
      expect(jsonSchema.properties?.id).toBeDefined();
      expect(jsonSchema.properties?.name).toBeDefined();
      expect(jsonSchema.properties?.email).toBeDefined();
      expect(jsonSchema.required).toContain('id');
      expect(jsonSchema.required).toContain('name');
      expect(jsonSchema.required).toContain('email');
      expect(jsonSchema.required).toContain('roles');
    });
  });
});
