// Fixture UI membership only; API permissions use real Django session/membership.
export const useUserPermissions = () => ({ allowPermissions: () => !["guest", "outsider"].includes(new URLSearchParams(window.location.search).get("mode") ?? "author") });

export const useUser = () => ({ data: { id: "isolated-browser-author" } });
