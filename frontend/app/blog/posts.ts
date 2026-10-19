import { createApiClient, DEFAULT_API_BASE_URL, type PostType } from "@homexo/shared";

// Blog pages render on the server, which may reach the API at a different address than browsers do.
export const serverApi = createApiClient(process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);

export const POST_TYPE_TABS: { value: PostType | null; label: string; href: string }[] = [
  { value: null, label: "All", href: "/blog" },
  { value: "article", label: "Articles", href: "/blog?type=article" },
  { value: "case_study", label: "Case studies", href: "/blog?type=case_study" },
];

const longDate = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "long", year: "numeric" });
export const formatPostDate = (iso: string | null) => (iso ? longDate.format(new Date(iso)) : "");
