"""
测试 BrainAgent
"""
import json
import os
import sys

# 将项目根目录添加到 Python 路径
sys.path.insert(0, '/home/data/icode/baidu/miaobi/multi_agent')

from agents.brain.process import BrainAgent


def test_brain_agent():
    """测试 BrainAgent 基本功能"""
    # 1. 读取输入文件
    input_path = "/home/data/icode/baidu/miaobi/multi_agent/inputs/医美项目对比.json"
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    query = data['query']
    user_input = f"""
    [query]
    {query}
    [requirements]
    {data['requirements']}
    [images]
    {data['images'] if data.get('images') else '无'}
    """
    task_type = data['task_type']

    print(f"📋 任务信息:")
    print(f"  - query: {query}")
    print(f"  - task_type: {task_type}")
    print(f"  - requirements: {data['requirements']}")

    # 2. 设置保存目录
    save_dir = f"/home/data/icode/baidu/miaobi/multi_agent/outputs/{query}_{task_type}"
    os.makedirs(save_dir, exist_ok=True)

    # 3. 初始化 BrainAgent
    print("\n🚀 初始化 BrainAgent...")
    agent = BrainAgent(
        model="deepseek-v3.2",
        audience="大众",
        language="中文",
        save_dir=save_dir
    )

    # 4. 运行 BrainAgent
    print("\n🎯 开始执行任务...")
    try:
        result = agent.run(
            query=query,
            user_input=user_input,
            task_type=task_type
        )

        print("\n" + "=" * 50)
        print("✅ 测试完成!")
        print(f"📝 执行结果: {result[:500]}..." if len(result) > 500 else f"📝 执行结果: {result}")
        print("=" * 50)

        return result

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_brain_agent_with_skill():
    """测试 BrainAgent 使用 Skill"""
    # 使用带 Skill 的方式测试

    # 1. 读取输入文件
    input_path = "/home/data/icode/baidu/miaobi/multi_agent/inputs/新手小白相机推荐.json"
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    query = data['query']
    user_input = f"""
    [query]
    {query}
    [requirements]
    {data['requirements']}
    [images]
    {data['images'] if data.get('images') else '无'}
    """
    task_type = data['task_type']

    # 2. 设置保存目录
    save_dir = f"/home/data/icode/baidu/miaobi/multi_agent/outputs/{query}_{task_type}_skill"
    os.makedirs(save_dir, exist_ok=True)

    # 3. 初始化 BrainAgent（使用 Skill）
    print("\n🚀 初始化 BrainAgent（使用Skill模式）...")
    agent = BrainAgent(
        model="deepseek-v3.2",
        audience="大众",
        language="中文",
        save_dir=save_dir,
        skills_dir="skills"  # 指定 Skill 目录
    )

    # 4. 运行 BrainAgent
    print("\n🎯 开始执行任务...")
    try:
        result = agent.run(
            query=query,
            user_input=user_input,
            task_type="笔记"  # 指定使用笔记 Skill
        )

        print("\n" + "=" * 50)
        print("✅ Skill模式测试完成!")
        print(f"📝 执行结果: {result[:500]}..." if len(result) > 500 else f"📝 执行结果: {result}")
        print("=" * 50)

        return result

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("开始测试 BrainAgent")
    print("=" * 60)

    print("\n" + "=" * 60)
    print("测试1: 基本功能")
    print("=" * 60)
    test_brain_agent()

    print("\n\n" + "=" * 60)
    print("测试2: 使用 Skill 模式")
    print("=" * 60)
    # test_brain_agent_with_skill()  # 可选测试

    print("\n\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)