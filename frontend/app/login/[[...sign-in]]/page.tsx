import { SignIn } from "@clerk/nextjs";

export default function LoginPage() {
  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        background: "var(--black)",
        color: "var(--white)",
        alignItems: "center",
        justifyContent: "center",
        backgroundImage: 'url("/ferrox-industrial-pump.jpg")',
        backgroundSize: "cover",
        backgroundPosition: "62% center",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(135deg, rgba(6,7,6,0.98) 0%, rgba(6,7,6,0.85) 100%)",
        }}
      />

      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: "100%",
          display: "flex",
          justifyContent: "center",
          padding: "48px 40px",
        }}
      >
        <SignIn
          path="/login"
          routing="path"
          fallbackRedirectUrl="/workspace"
        />
      </div>
    </div>
  );
}
