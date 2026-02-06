/**
 * Human-in-the-loop (agent asks user questions).
 *
 * Run: npx ts-node examples/11_human_in_the_loop.ts
 */
import { Agent } from '../src';

const agent = new Agent({ name: 'Wizard', description: 'Interactive wizard' });

agent.skill('setup_wizard', { description: 'Multi-step wizard' }, async ({ name, role, confirmed }: { name?: string; role?: string; confirmed?: boolean }) => {
  if (!name) return { status: 'input_required', question: "What's your name?", field: 'name' };
  if (!role) return { status: 'input_required', question: "What's your role?", field: 'role', options: ['Developer', 'Designer', 'Manager', 'Other'] };
  if (confirmed === undefined) return { status: 'input_required', question: 'Create profile for ' + name + ' (' + role + ')?', field: 'confirmed', type: 'confirm' };
  return confirmed ? { status: 'created', name, role } : { status: 'cancelled' };
});

agent.skill('book_flight', { description: 'Book a flight' }, async ({ destination, date, travel_class, confirmed }: { destination: string; date?: string; travel_class?: string; confirmed?: boolean }) => {
  if (!date) return { status: 'input_required', question: 'Travel date? (YYYY-MM-DD)', field: 'date' };
  if (!travel_class) return { status: 'input_required', question: 'Which class?', field: 'travel_class', options: ['Economy', 'Business', 'First'] };
  if (confirmed === undefined) return { status: 'input_required', question: 'Book ' + travel_class + ' to ' + destination + ' on ' + date + '?', field: 'confirmed', type: 'confirm' };
  return confirmed ? { status: 'booked', destination, date, class: travel_class, confirmation: 'ABC123' } : { status: 'cancelled' };
});

agent.run({ port: 8787 });
