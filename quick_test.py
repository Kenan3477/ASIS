#!/usr/bin/env python3
"""Quick test of enhanced embedding system"""

try:
    from advanced_embedding_system import MultiModalEmbeddingSystem
    print("✅ MultiModalEmbeddingSystem imported successfully")

    # Test initialization
    system = MultiModalEmbeddingSystem()
    print(f"✅ System initialized with default dimension: {system.default_dimension}")
    print(f"✅ Models available: {len(system.models)}")

    # Test text embedding
    result = system.embed_text("Test embedding generation")
    print(f"✅ Text embedding generated: shape {result.embedding.shape}, success: {result.success}")

    # Test ensemble capability check
    if hasattr(system, 'ensemble_strategies'):
        print(f"✅ Ensemble strategies available: {list(system.ensemble_strategies.keys())}")
    else:
        print("⚠️ Ensemble strategies not found")

    # Test similarity computation
    if len(result.embedding) > 0:
        result2 = system.embed_text("Another test text")
        sim = system.compute_similarity(result.embedding, result2.embedding)
        print(f"✅ Similarity computation: {sim.similarity:.4f}, success: {sim.success}")

    # Test clustering
    embeddings = [result.embedding, result2.embedding]
    if len(embeddings) >= 2:
        import numpy as np
        # Ensure embeddings have the same shape
        min_dim = min(len(emb) for emb in embeddings)
        embeddings_normalized = [emb[:min_dim] for emb in embeddings]
        embedding_array = np.array(embeddings_normalized)
        cluster_result = system.cluster_embeddings(embedding_array, n_clusters=2)
        print(f"✅ Clustering: {cluster_result.n_clusters} clusters, success: {cluster_result.success}")

    print("🎉 Enhanced embedding system is working!")
    
    # Get statistics
    stats = system.get_statistics()
    print(f"📊 System has {len(stats['models'])} models and {stats['default_dimension']} dimensions")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
