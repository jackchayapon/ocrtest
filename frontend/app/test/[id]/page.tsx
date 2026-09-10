import TestingWorkspace from "@/components/TestingWorkspace";

export default async function TestDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TestingWorkspace initialTestCaseId={id} />;
}
