"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

export type Identity = { company_name: string; platform_name: string };
const FALLBACK: Identity = { company_name: process.env.NEXT_PUBLIC_COMPANY_NAME || "Demonkoncernen AB", platform_name: "Rocky" };
let cached: Identity | null = null;

/** Company identity comes from the backend (COMPANY_NAME / PLATFORM_NAME) so one setting renames everything. */
export function useIdentity(): Identity {
  const [id, setId] = useState<Identity>(cached ?? FALLBACK);
  useEffect(() => {
    if (cached) return;
    api<Identity>("/api/auth/status").then((r) => { cached = { company_name: r.company_name, platform_name: r.platform_name }; setId(cached); }).catch(() => {});
  }, []);
  useEffect(() => { document.title = `${id.company_name} · ${id.platform_name} Commerce Intelligence`; }, [id]);
  return id;
}
