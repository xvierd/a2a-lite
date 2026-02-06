/**
 * Using TypeScript interfaces for type-safe inputs/outputs.
 *
 * Run: npx ts-node examples/06_typed_models.ts
 */
import { Agent } from '../src';

interface User { name: string; email: string; age: number; }
const usersDb: User[] = [];

const agent = new Agent({ name: 'UserService', description: 'Manages users' });

agent.skill('create_user', { description: 'Create a new user' }, async ({ user }: { user: User }) => {
  usersDb.push(user);
  return { id: usersDb.length, user, message: `Created ${user.name}` };
});

agent.skill('list_users', { description: 'List all users' }, async () => usersDb);

agent.skill('find_user', { description: 'Find user by name' }, async ({ name }: { name: string }) =>
  usersDb.find(u => u.name.toLowerCase() === name.toLowerCase()) || null);

agent.run({ port: 8787 });
