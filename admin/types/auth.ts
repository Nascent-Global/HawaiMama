import { z } from "zod";

export const AdminPermissionsSchema = z.object({
  can_view_live: z.boolean(),
  can_manage_feeds: z.boolean(),
  can_view_violations: z.boolean(),
  can_verify_violations: z.boolean(),
  can_view_accidents: z.boolean(),
  can_verify_accidents: z.boolean(),
  can_view_challans: z.boolean(),
  can_manage_admins: z.boolean(),
});

export const AdminAccountSchema = z.object({
  id: z.string(),
  username: z.string(),
  full_name: z.string(),
  role: z.enum(["superadmin", "admin"]),
  is_active: z.boolean(),
  all_locations: z.boolean(),
  allowed_locations: z.array(z.string()),
  permissions: AdminPermissionsSchema,
});

export const LoginResponseSchema = z.object({
  admin: AdminAccountSchema,
  token: z.string(),
});

export type AdminPermissions = z.infer<typeof AdminPermissionsSchema>;
export type AdminAccount = z.infer<typeof AdminAccountSchema>;
export type LoginResponse = z.infer<typeof LoginResponseSchema>;
