import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <SignIn
        appearance={{
          elements: {
            rootBox: "mx-auto",
            card: "bg-[var(--panel)] border border-[var(--line)] shadow-none",
          },
        }}
      />
    </div>
  );
}
