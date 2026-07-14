"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorText } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Plus } from "lucide-react";

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  initial_password?: string | null;
}

const ALL_ROLES = ["hr_admin", "test_creator", "evaluator"] as const;

export default function UsersPage() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [roles, setRoles] = useState<Set<string>>(new Set(["hr_admin"]));
  const [created, setCreated] = useState<UserRow | null>(null);

  const { data } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api<{ items: UserRow[] }>("/admin/users", { token: "admin" }),
  });

  const create = useMutation({
    mutationFn: () =>
      api<UserRow>("/admin/users", {
        token: "admin",
        body: { email, full_name: fullName, roles: Array.from(roles) },
      }),
    onSuccess: (user) => {
      setCreated(user);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => toast.error(errorText(error)),
  });

  function toggleRole(role: string) {
    const next = new Set(roles);
    if (next.has(role)) next.delete(role);
    else next.add(role);
    setRoles(next);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Admin Users</h1>
          <p className="text-sm text-muted-foreground">
            Every admin holds one or more roles; permissions are the union of roles.
          </p>
        </div>
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) {
              setCreated(null);
              setEmail("");
              setFullName("");
            }
          }}
        >
          <DialogTrigger render={<Button className="gap-2" />}>
            <Plus className="h-4 w-4" /> New admin
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New admin user</DialogTitle>
            </DialogHeader>
            {created ? (
              <div className="space-y-3">
                <p className="text-sm">Account created. Temporary password (shown once):</p>
                <div className="rounded bg-muted p-3 font-mono text-sm">
                  {created.initial_password}
                </div>
                <Button className="w-full" onClick={() => setOpen(false)}>
                  Done
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Full name</Label>
                  <Input value={fullName} onChange={(e) => setFullName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Roles</Label>
                  {ALL_ROLES.map((role) => (
                    <label key={role} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={roles.has(role)}
                        onChange={() => toggleRole(role)}
                      />
                      {role}
                    </label>
                  ))}
                </div>
                <Button
                  className="w-full"
                  onClick={() => create.mutate()}
                  disabled={!email || !fullName || roles.size === 0 || create.isPending}
                >
                  Create
                </Button>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
      <div className="rounded-lg border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Roles</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.items.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-medium">{user.full_name}</TableCell>
                <TableCell>{user.email}</TableCell>
                <TableCell className="space-x-1">
                  {user.roles.map((role) => (
                    <Badge key={role} variant="outline">
                      {role}
                    </Badge>
                  ))}
                </TableCell>
                <TableCell>
                  <Badge variant={user.is_active ? "default" : "secondary"}>
                    {user.is_active ? "active" : "disabled"}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
