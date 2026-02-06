import com.a2alite.Agent;
import com.a2alite.testing.TestClient;
import java.util.Map;

/**
 * Testing your agents with TestClient.
 *
 * Run: ./gradlew run -PmainClass=Testing
 */
class Testing {
    public static void main(String[] args) throws Exception {
        var agent = Agent.builder().name("Calculator").description("Math operations").build();

        agent.skill("add", params -> ((Number) params.get("a")).intValue() + ((Number) params.get("b")).intValue());
        agent.skill("multiply", params -> ((Number) params.get("a")).intValue() * ((Number) params.get("b")).intValue());
        agent.skill("divide", params -> {
            double b = ((Number) params.get("b")).doubleValue();
            if (b == 0) return Map.of("error", "Cannot divide by zero");
            return Map.of("result", ((Number) params.get("a")).doubleValue() / b);
        });

        System.out.println("Running tests...\n");
        var client = new TestClient(agent);

        assert client.call("add", Map.of("a", 2, "b", 3)).equals(5) : "add failed";
        System.out.println("✅ test_add passed");

        assert client.call("multiply", Map.of("a", 4, "b", 5)).equals(20) : "multiply failed";
        System.out.println("✅ test_multiply passed");

        @SuppressWarnings("unchecked")
        var divResult = (Map<String, Object>) client.call("divide", Map.of("a", 10, "b", 2));
        assert divResult.get("result").equals(5.0) : "divide failed";
        System.out.println("✅ test_divide passed");

        @SuppressWarnings("unchecked")
        var zeroResult = (Map<String, Object>) client.call("divide", Map.of("a", 10, "b", 0));
        assert zeroResult.containsKey("error") : "divide by zero failed";
        System.out.println("✅ test_divide_by_zero passed");

        assert client.listSkills().containsAll(java.util.List.of("add", "multiply", "divide"));
        System.out.println("✅ test_list_skills passed");

        System.out.println("\n🎉 All tests passed!");
    }
}
