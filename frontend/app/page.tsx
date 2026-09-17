import { CadStudio } from "../components/CadStudio";

export default function Page() {
  return <main><CadStudio apiBaseUrl={process.env.NEXT_PUBLIC_CAD_API_URL ?? ""} /></main>;
}
