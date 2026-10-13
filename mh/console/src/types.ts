export interface SlotState {
  id: string;
  account_id: string;
  run_mode: string;
  sandbox_name: string;
  status: string;
  detail: string;
  task_id: string;
  character_id: string;
  character_name: string;
  screenshot_url: string | null;
  updated_at: number;
}
