// Fixture UI membership only; API permissions use the real Django session and membership.
export const useUserPermissions = () => ({
  allowPermissions: () => new URLSearchParams(window.location.search).get("mode") !== "guest",
});
export const useUser = () => ({ data: { id: new URLSearchParams(window.location.search).get("mode") ?? "author" } });
