import enUS from "@/src/locales/en-US.json";
import zhCN from "@/src/locales/zh-CN.json";
import zhTW from "@/src/locales/zh-TW.json";
import type { Locale } from "./types";

const dictionaries: Record<Locale, Record<string, string>> = {
  "zh-TW": zhTW,
  "zh-CN": zhCN,
  "en-US": enUS,
};

export function chooseLocale(input?: string | null): Locale {
  if (input?.toLowerCase().startsWith("zh-cn") || input?.toLowerCase().startsWith("zh-sg")) return "zh-CN";
  if (input?.toLowerCase().startsWith("zh")) return "zh-TW";
  return "en-US";
}

export function translate(locale: Locale, key: string, values?: Record<string, string | number>): string {
  let value = dictionaries[locale][key] ?? dictionaries["en-US"][key] ?? key;
  for (const [name, replacement] of Object.entries(values ?? {})) {
    value = value.replaceAll(`{${name}}`, String(replacement));
  }
  return value;
}
