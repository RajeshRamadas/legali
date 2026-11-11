export type ManagedService = {
  id: string; slug: string; name: string; category: string; description: string;
  active: boolean; paused: boolean; revision: number;
  description_revision: number; description_customized: boolean; default_description: string;
};
