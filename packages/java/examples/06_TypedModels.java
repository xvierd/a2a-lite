import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.*;

/**
 * Using typed models (Java records) for type-safe inputs/outputs.
 *
 * Run: ./gradlew run -PmainClass=TypedModels
 */
class TypedModels {
    record User(String name, String email, int age) {}
    private static final List<User> usersDb = new ArrayList<>();

    public static void main(String[] args) {
        var agent = Agent.builder().name("UserService").description("Manages users").build();

        agent.skill("create_user", SkillConfig.of("Create a new user"), params -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> u = (Map<String, Object>) params.get("user");
            var user = new User((String) u.get("name"), (String) u.get("email"), ((Number) u.get("age")).intValue());
            usersDb.add(user);
            return Map.of("id", usersDb.size(), "user", Map.of("name", user.name(), "email", user.email()), "message", "Created " + user.name());
        });

        agent.skill("list_users", SkillConfig.of("List all users"), params ->
            usersDb.stream().map(u -> Map.of("name", u.name(), "email", u.email(), "age", u.age())).toList());

        agent.skill("find_user", SkillConfig.of("Find user by name"), params -> {
            String name = (String) params.get("name");
            return usersDb.stream().filter(u -> u.name().equalsIgnoreCase(name)).findFirst()
                .map(u -> (Object) Map.of("name", u.name(), "email", u.email())).orElse(null);
        });

        agent.run(8787);
    }
}
