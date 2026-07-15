export interface McqOption {
  id: string;
  text: string;
}

export interface TestCase {
  id: string;
  input?: string;
  expected_output?: string;
  is_hidden?: boolean;
  weight?: number;
}

export interface QuestionConfig {
  options?: McqOption[];
  correct_option_ids?: string[];
  rubric?: string;
  expected_answer?: string;
  allowed_languages?: string[];
  starter_code?: Record<string, string>;
  test_cases?: TestCase[];
}

export interface QuestionVersionOut {
  id: string;
  version: number;
  qtype: "mcq" | "text" | "coding";
  category: string;
  answer_type: string;
  difficulty: string;
  title: string;
  body: string;
  config: QuestionConfig;
  topic: string;
  skills: string[];
  tags: string[];
}

export interface QuestionOut {
  id: string;
  status: string;
  source: string;
  approved_by: string | null;
  current_version: QuestionVersionOut | null;
  quality_flags?: { kind: string; detail: Record<string, unknown> }[];
}

export interface SectionOut {
  id: string;
  order_index: number;
  name: string;
  description: string;
  duration_min: number;
  weightage_pct: number;
  question_count: number;
  is_final: boolean;
  questions: { question_version_id: string; pool_group: string | null; points: number }[];
  pool_rules: { pool_group: string; select_count: number }[];
}

export interface AssessmentOut {
  id: string;
  title: string;
  description: string;
  window_start_at: string | null;
  window_end_at: string | null;
  status: string;
  settings: Record<string, unknown>;
  version: {
    id: string;
    version: number;
    frozen: boolean;
    total_duration_min: number;
    published_at: string | null;
    sections: SectionOut[];
  } | null;
}

export interface AssignmentOut {
  id: string;
  candidate: {
    id: string;
    student_id: string | null;
    full_name: string;
    email: string;
    phone: string;
    cgpa: number | null;
  };
  window_start_at: string;
  window_end_at: string;
  status: string;
  username: string;
  credentials_expired: boolean;
  send_email: boolean;
  initial_password?: string;
  email_status?: "sent" | "failed" | "not_sent";
}

export interface ExamQuestion {
  session_question_id: string;
  section_id: string;
  order_index: number;
  qtype: "mcq" | "text" | "coding";
  answer_type: string;
  title: string;
  body: string;
  config: QuestionConfig;
  points: number;
  state: "unseen" | "seen" | "answered" | "marked_review";
  saved_answer: Record<string, unknown> | null;
}

export interface ExamSection {
  section_id: string;
  name: string;
  order_index: number;
  status: "locked" | "active" | "submitted" | "auto_submitted";
  duration_min: number;
  deadline_at: string | null;
  is_final: boolean;
}

export interface ExamState {
  session_id: string;
  status: string;
  server_now: string;
  ends_at: string;
  current_section_id: string | null;
  sections: ExamSection[];
  questions: ExamQuestion[];
}

export interface CaseResultOut {
  case_id: string;
  passed: boolean;
  status: string;
  stdout: string;
  stderr: string;
  time_ms: number;
  memory_kb: number;
  hidden?: boolean;
}

export interface CodeRunOut {
  submission_id: string;
  status: string;
  results: CaseResultOut[];
  passed_count?: number;
  total_count?: number;
  score?: number | null;
  exec_time_ms: number;
}

export interface SectionScore {
  section_id: string;
  name: string;
  weightage_pct: number;
  score: number;
  max: number;
  time_spent_sec: number;
  attempted: number;
  unattempted: number;
  correct: number;
  wrong: number;
}

export interface ReportOut {
  report_id: string;
  candidate: { full_name: string; email: string };
  assessment: { id: string; title: string };
  session: { id: string; status: string; started_at: string; submitted_at: string | null };
  overall_score: number;
  overall_max: number;
  section_scores: SectionScore[];
  ai_observations: string;
  red_flag_count: number;
  warning_count: number;
  percentile: number | null;
  rank: number | null;
  status: string;
  proctoring_timeline: { kind: string; severity: string; occurred_at: string }[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}
