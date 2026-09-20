export type ColumnId = "backlog" | "in-progress" | "cab" | "deployed";

export type Category = "Network" | "Security" | "Incident" | "Access" | "Planning";

export type Priority = "P1" | "P2";

export type TicketPrefix = "CHG" | "INC" | "TASK";

export interface CardData {
  id: string;
  ticketId: string;
  title: string;
  category: Category;
  priority?: Priority;
  assignee: string;
  dueDate: string;
  progress?: number;
  columnId: ColumnId;
}

export interface ColumnDef {
  id: ColumnId;
  title: string;
}
