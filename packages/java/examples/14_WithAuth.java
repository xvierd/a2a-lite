import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.a2alite.auth.APIKeyAuth;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Authentication (optional).
 *
 * Run: ./gradlew run -PmainClass=WithAuth
 * Test: curl -H "X-API-Key: secret-key" http://localhost:8787/
 */
class WithAuth {
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("SecureBot")
            .description("Bot with authentication")
            .auth(new APIKeyAuth(Set.of("secret-key", "another-key")))
            .build();

        agent.skill("public_info", SkillConfig.of("Available to authenticated users"),
            params -> Map.of("message", "You're authenticated!"));

        agent.skill("get_secrets", SkillConfig.of("Get secret data"),
            params -> Map.of("secrets", List.of("secret1", "secret2"), "message", "Authenticated only"));

        System.out.println("Test with: curl -H 'X-API-Key: secret-key' http://localhost:8787/");
        agent.run(8787);
    }
}
